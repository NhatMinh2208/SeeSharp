using System.Text.Json;
using System.IO.Compression;
using SeeSharp.Common;
namespace SeeSharp.Blender;
public class FullSceneRequestHandler : IBlenderEventHandler {
    private readonly IServiceProvider _services;
    public string EventType => "request_full_scene";
    public FullSceneRequestHandler(IServiceProvider services)
    {
        _services = services;
    }
    
    async public void RequestFullScene(string scene)
    {
        Logger.Log($"[Sync] Blender requested full scene: {scene}");

        string sceneDirectory = Path.Combine(
            Environment.GetEnvironmentVariable("SEESHARP_SCENE_DIRS"),
            scene
        );

        string zipPath = Path.Combine(
            Path.GetTempPath(),
            $"{Path.GetFileName(Path.TrimEndingDirectorySeparator(sceneDirectory))}_{Guid.NewGuid():N}.zip"
        );

        ZipFile.CreateFromDirectory(
            sceneDirectory,
            zipPath,
            CompressionLevel.Optimal,
            includeBaseDirectory: false
        );
        var sender = (BlenderCommandSender)_services.GetService(typeof(BlenderCommandSender))!;
        try
        {
            await sender.SendArchiveAsync(zipPath, scene);
        }
        finally
        {
            if (File.Exists(zipPath))
                File.Delete(zipPath);
        }
    }

    public void Handle(JsonElement root)
    {
        string scene = root.GetProperty("scene").GetString()!;
        RequestFullScene(scene);
    }
}
