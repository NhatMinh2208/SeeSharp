using System.IO.Compression;
using System.Text.Json;
using SeeSharp.Common;
namespace SeeSharp.Blender;

public class SceneUpdateHandler : IBlenderArchiveEventHandler
{
    private readonly string _sceneRoot;

    public string EventType => "scene_update";

    public SceneUpdateHandler(string sceneRoot)
    {
        _sceneRoot = sceneRoot;
    }

    public async Task HandleAsync(JsonElement root, byte[] archive)
    {
        string sceneName = root.GetProperty("sceneName").GetString()
            ?? throw new InvalidDataException("Missing scene name.");

        string sceneDirectory = Path.GetFullPath(
            Path.Combine(_sceneRoot, sceneName));

        // Ensure the scene directory remains inside the configured root.
        string rootPath = Path.GetFullPath(_sceneRoot)
            .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;

        if (!sceneDirectory.StartsWith(
                rootPath, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Invalid scene directory.");

        Directory.CreateDirectory(sceneDirectory);

        // Extract updated files.
        using (var memoryStream = new MemoryStream(archive))
        using (var zip = new ZipArchive(
            memoryStream, ZipArchiveMode.Read))
        {
            foreach (var entry in zip.Entries)
            {
                string destination = Path.GetFullPath(
                    Path.Combine(sceneDirectory, entry.FullName));

                // Prevent ZIP path traversal.
                if (!destination.StartsWith(
                        rootPath, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException(
                        $"Invalid ZIP entry: {entry.FullName}");

                if (entry.FullName.EndsWith('/'))
                {
                    Directory.CreateDirectory(destination);
                    continue;
                }

                Directory.CreateDirectory(
                    Path.GetDirectoryName(destination)!);

                await using var source = entry.Open();
                await using var target = File.Create(destination);

                await source.CopyToAsync(target);
            }
        }

        // Delete files no longer present in the local scene.
        // foreach (var item in root.GetProperty("deleted").EnumerateArray())
        // {
        //     string relativePath = item.GetString()
        //         ?? throw new InvalidDataException("Invalid deleted path.");

        //     string destination = Path.GetFullPath(
        //         Path.Combine(sceneDirectory, relativePath));

        //     if (!destination.StartsWith(
        //             rootPath, StringComparison.OrdinalIgnoreCase))
        //         throw new InvalidDataException(
        //             $"Invalid deleted path: {relativePath}");

        //     if (File.Exists(destination))
        //         File.Delete(destination);
        // }

        Logger.Log($"✅ Remote scene '{sceneName}' updated.");
    }
}