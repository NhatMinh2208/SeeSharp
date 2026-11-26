using System.Security.Cryptography;
using System.Text.Json;
using SeeSharp.Common;
namespace SeeSharp.Blender;
public sealed class SceneManifest
{
    public string SceneName { get; set; } = "";
    public DateTime GeneratedAt { get; set; }
    public List<SceneAsset> Assets { get; set; } = new();
}

public sealed class SceneAsset
{
    public string Path { get; set; } = "";
    public string Sha256 { get; set; } = "";
    public long Size { get; set; }
}

public static class SceneManifestManager
{
    public static SceneManifest Generate(string sceneFolder)
    {
        string root = Path.GetFullPath(sceneFolder);

        if (!Directory.Exists(root))
            throw new DirectoryNotFoundException(root);

        string manifestPath = Path.Combine(root, "manifest.json");

        var manifest = new SceneManifest
        {
            SceneName = new DirectoryInfo(root).Name,
            GeneratedAt = DateTime.UtcNow
        };

        foreach (string file in Directory.EnumerateFiles(
                    root, "*", SearchOption.AllDirectories))
        {
            // Do not include the manifest itself.
            if (string.Equals(
                    Path.GetFullPath(file),
                    manifestPath,
                    StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            // Store relative paths so the manifest works on other machines.
            string relativePath = Path.GetRelativePath(root, file)
                .Replace('\\', '/');

            using var stream = File.OpenRead(file);
            string hash = Convert.ToHexString(
                SHA256.HashData(stream)).ToLowerInvariant();

            manifest.Assets.Add(new SceneAsset
            {
                Path = relativePath,
                Sha256 = hash,
                Size = new FileInfo(file).Length
            });
        }

        manifest.Assets = manifest.Assets
            .OrderBy(a => a.Path, StringComparer.Ordinal)
            .ToList();

        string json = JsonSerializer.Serialize(
            manifest,
            new JsonSerializerOptions
            {
                WriteIndented = true
            });

        File.WriteAllText(manifestPath, json);

        return manifest;
    }

    async public static Task SendManifestAsync(BlenderCommandSender sender, string manifestPath)
    {
        if (!File.Exists(manifestPath))
        {
            Logger.Warning($"Manifest not found: {manifestPath}");
            return;
        }

        string jsonContent = await File.ReadAllTextAsync(manifestPath);

        var command = new
        {
            command = "sync_manifest",
            data = jsonContent
        };
        await sender.SendCommandAsync(command);
        Logger.Log($"➡ Sent manifest: {Path.GetFileName(manifestPath)}");
    }
}