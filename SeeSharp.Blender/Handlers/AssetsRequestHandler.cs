using System.Text.Json;
using System.IO.Compression;
namespace SeeSharp.Blender;
public class AssetsRequestHandler : IBlenderEventHandler {
    private readonly IServiceProvider _services;
    public string EventType => "request_assets";
    public AssetsRequestHandler(IServiceProvider services)
    {
        _services = services;
    }

    async public void RequestAssets(string scene, List<string> files)
    {
        string CreateAssetsZip(string sceneDirectory,IEnumerable<string> requestedFiles)
        {
            string zipPath = Path.Combine(
                Path.GetTempPath(),
                $"SceneAssets_{Guid.NewGuid():N}.zip"
            );

            string root = Path.GetFullPath(sceneDirectory)
                .TrimEnd(Path.DirectorySeparatorChar)
                + Path.DirectorySeparatorChar;

            using (var archive = ZipFile.Open(zipPath, ZipArchiveMode.Create))
            {
                foreach (string relativePath in requestedFiles)
                {
                    // Prevent paths from escaping the scene directory.
                    string fullPath = Path.GetFullPath(
                        Path.Combine(root, relativePath)
                    );

                    if (!fullPath.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException(
                            $"Invalid asset path: {relativePath}"
                        );

                    if (!File.Exists(fullPath))
                    {
                        throw new FileNotFoundException(
                            $"Requested asset does not exist: {relativePath}",
                            fullPath
                        );
                    }

                    // Preserve the relative directory structure inside the ZIP.
                    string entryName = relativePath.Replace('\\', '/');

                    archive.CreateEntryFromFile(
                        fullPath,
                        entryName,
                        CompressionLevel.Optimal
                    );
                }
                // Always include the latest server manifest.
                string manifestPath = Path.Combine(root, "manifest.json");

                if (!File.Exists(manifestPath))
                    throw new FileNotFoundException("Server manifest not found.", manifestPath);
                archive.CreateEntryFromFile(
                    manifestPath,
                    "manifest.json",
                    CompressionLevel.Optimal
                );
            }
            return zipPath;
        }
        // Create ZIP containing requested files
        string zipPath = CreateAssetsZip(
            Path.Combine(
                Environment.GetEnvironmentVariable("SEESHARP_SCENE_DIRS"),
                scene
            ),
            files
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

        List<string> files = root.GetProperty("files")
            .EnumerateArray()
            .Select(x => x.GetString()!)
            .ToList();

        RequestAssets(scene, files);
    }
}
