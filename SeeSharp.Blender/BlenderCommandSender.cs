using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using SeeSharp.Common;
namespace SeeSharp.Blender;
public class BlenderCommandSender {
    private readonly BlenderEventListener _eventListener;

    public BlenderCommandSender(BlenderEventListener eventListener)
    {
        _eventListener = eventListener;
    }

    public bool IsConnected => _eventListener.IsConnected;

    public async Task SendCommandAsync(object cmd)
    {
        try
        {
            string json = JsonSerializer.Serialize(cmd) + "\n";
            byte[] bytes = Encoding.UTF8.GetBytes(json);

            await _eventListener.SendAsync(bytes);

            Logger.Log("➡ Sent command to Blender: " + json);
        }
        catch (Exception ex)
        {
            Logger.Error("❌ Error sending command: " + ex.Message);
        }
    }

    public async Task SendCursorAsync(float x, float y, float z)
    {
        var data = new
        {
            cursor_position = new[] { x, y, z }
        };

        await SendCommandAsync(data);
    }

    public async Task SendArchiveAsync(string zipPath, string sceneName)
    {
        await _eventListener.SendArchiveAsync(zipPath, sceneName);
    }
}
