using System.Net.Sockets;
using System.Net;
using System.Text;
using System.Text.Json;
using SeeSharp.Common;
namespace SeeSharp.Blender;
public class BlenderEventListener {
    private TcpListener? _listener;
    private BlenderEventDispatcher _dispatcher;
    private TaskCompletionSource<bool>? _blenderReady;
    private const long MaxArchiveSize = 1024L * 1024 * 1024; // 1 GiB

    private TcpClient? _blenderClient;
    private NetworkStream? _blenderStream;

    private readonly object _connectionLock = new();
    private readonly SemaphoreSlim _sendLock = new(1,1);
    private bool _connected;
    public bool IsConnected => _connected;
    public string? BlenderIPAddress { get; private set; }


    public BlenderEventListener(BlenderEventDispatcher dispatcher) {
        _dispatcher = dispatcher;
    }

    public void RegisterDispatcher(BlenderEventDispatcher dispatcher) {
        _dispatcher = dispatcher;
    }

    public async Task StartAsync() {
        // _listener = new TcpListener(IPAddress.Loopback, 5052);
        _listener = new TcpListener(IPAddress.Any, 5052);
        _listener.Start();
        Logger.Log("📡 Listening for Blender events on 5052...");

        _ = Task.Run(async () => 
        {
            while (true)
            {
                var client = await _listener.AcceptTcpClientAsync();

                lock (_connectionLock)
                {
                    // Replace the previous client if necessary.
                    _blenderClient?.Close();

                    _blenderClient = client;
                    _blenderStream = client.GetStream();
                    _connected = true;

                    BlenderIPAddress =
                        ((IPEndPoint)client.Client.RemoteEndPoint!).Address.ToString();
                }

                Logger.Log($"🔌 Blender connected: {BlenderIPAddress}");

                _blenderReady?.TrySetResult(true);

                // Handle incoming events without blocking acceptance.
                _ = HandleClientAsync(client);
            }
        }); 
    }

    private async Task HandleClientAsync(TcpClient client)
    {
        NetworkStream stream = client.GetStream();
        try
        {
            while (true)
            {
                // Read only the JSON header, without buffering ZIP bytes.
                string? line = await ReadLineAsync(stream);

                if (line == null)
                    break;

                using var doc = JsonDocument.Parse(line);
                JsonElement root = doc.RootElement;

                Logger.Log("📨 Received event: " + line);

                if (root.TryGetProperty("archiveSize", out var sizeElement))
                {
                    long archiveSize = sizeElement.GetInt64();

                    if (archiveSize < 0 || archiveSize > MaxArchiveSize)
                        throw new InvalidDataException(
                            $"Invalid archive size: {archiveSize}");

                    byte[] archive = await ReadExactAsync(
                        stream, checked((int)archiveSize));

                    await _dispatcher.DispatchArchiveAsync(root, archive);

                    // Confirm that the archive handler completed.
                    await WriteLineAsync(stream, """{"event":"archive_received","success":true}""");
                }
                else
                {
                    // Existing JSON event behavior.
                    _dispatcher.Dispatch(root);
                }
            }
        }
        catch (Exception ex)
        {
            Logger.Error("❌ Blender connection error: " + ex.Message);

            try
            {
                await WriteLineAsync(
                    stream,
                    JsonSerializer.Serialize(new
                    {
                        @event = "archive_received",
                        success = false,
                        error = ex.Message
                    }));
            }
            catch
            {
                // Connection may already be closed.
            }
        }
        finally
        {
            lock (_connectionLock)
            {
                // Only clear if this is still the active connection.
                if (ReferenceEquals(_blenderClient, client))
                {
                    _blenderClient = null;
                    _blenderStream = null;
                    _connected = false;
                    BlenderIPAddress = null;
                }
            }

            client.Close();
            Logger.Warning("🔌 Blender disconnected");
        }
    }

    public async Task SendArchiveAsync(string zipPath, string sceneName)
    {
        await _sendLock.WaitAsync();

        try
        {
            NetworkStream? stream = _blenderStream;

            if (!_connected || stream == null)
            {
                Logger.Warning("⚠ Blender is not connected.");
                return;
            }

            var fileInfo = new FileInfo(zipPath);

            if (!fileInfo.Exists)
            {
                Logger.Warning($"⚠ Archive not found: {zipPath}");
                return;
            }

            var header = new
            {
                command = "receive_archive",
                scene = sceneName,
                size = fileInfo.Length
            };

            byte[] headerBytes = Encoding.UTF8.GetBytes(
                JsonSerializer.Serialize(header) + "\n"
            );

            await stream.WriteAsync(headerBytes);

            await using var fileStream = new FileStream(
                zipPath,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 64 * 1024,
                useAsync: true
            );

            await fileStream.CopyToAsync(stream);
            await stream.FlushAsync();

            Logger.Log($"➡ Sent archive '{sceneName}' ({fileInfo.Length} bytes)");
        }
        catch (Exception ex)
        {
            Logger.Error("❌ Error sending archive: " + ex.Message);
            _connected = false;
        }
        finally
        {
            _sendLock.Release();
        }
    }

    private static async Task<string?> ReadLineAsync(NetworkStream stream)
    {
        using var buffer = new MemoryStream();
        byte[] oneByte = new byte[1];

        while (true)
        {
            int bytesRead = await stream.ReadAsync(oneByte, 0, 1);

            if (bytesRead == 0)
            {
                if (buffer.Length == 0)
                    return null;

                throw new EndOfStreamException("Incomplete JSON header.");
            }

            if (oneByte[0] == (byte)'\n')
                break;

            buffer.WriteByte(oneByte[0]);

            if (buffer.Length > 1024 * 1024)
                throw new InvalidDataException("JSON header is too large.");
        }

        return Encoding.UTF8.GetString(buffer.ToArray()).TrimEnd('\r');
    }

    private static async Task<byte[]> ReadExactAsync(
        NetworkStream stream, int size)
    {
        byte[] buffer = new byte[size];
        int totalRead = 0;

        while (totalRead < size)
        {
            int bytesRead = await stream.ReadAsync(
                buffer, totalRead, size - totalRead);

            if (bytesRead == 0)
                throw new EndOfStreamException("Incomplete ZIP archive.");

            totalRead += bytesRead;
        }

        return buffer;
    }

    private static async Task WriteLineAsync(
        NetworkStream stream, string message)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(message + "\n");
        await stream.WriteAsync(bytes, 0, bytes.Length);
    }

    public async Task SendAsync(byte[] bytes)
    {
        await _sendLock.WaitAsync();
        try
        {
            NetworkStream? stream = _blenderStream;

            if (!_connected || stream == null)
            {
                Logger.Warning("⚠ Blender is not connected.");
                return;
            }

            await stream.WriteAsync(bytes);
            await stream.FlushAsync();
        }
        catch (Exception ex)
        {
            Logger.Error("❌ Error sending data to Blender: " + ex.Message);
            _connected = false;
        }
        finally
        {
            _sendLock.Release();
        }
    }
    public async Task WaitForBlenderAsync()
    {
        _blenderReady = new TaskCompletionSource<bool>(
            TaskCreationOptions.RunContinuationsAsynchronously);

        await _blenderReady.Task;
    }
}