using System.Text.Json;
namespace SeeSharp.Blender;
public class AssetsRequestHandler : IBlenderEventHandler {
    public string EventType => "request_assets";
    public event Action<string, List<string>>? OnRequestAssets;
    public void Handle(JsonElement root)
    {
        string scene = root.GetProperty("scene").GetString()!;

        List<string> files = root.GetProperty("files")
            .EnumerateArray()
            .Select(x => x.GetString()!)
            .ToList();

        OnRequestAssets?.Invoke(scene, files);
    }
}
