using System.Text.Json;
namespace SeeSharp.Blender;
public class FullSceneRequestHandler : IBlenderEventHandler {
    public string EventType => "request_full_scene";
    public event Action<string>? OnRequestFullScene;
    public void Handle(JsonElement root)
    {
        string scene = root.GetProperty("scene").GetString()!;
        OnRequestFullScene?.Invoke(scene);
    }
}
