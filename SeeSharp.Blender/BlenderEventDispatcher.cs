using System.Text.Json;
using SeeSharp.Common;

namespace SeeSharp.Blender;

public interface IBlenderEventHandler {
    string EventType { get; }
    void Handle(JsonElement root);
}

public interface IBlenderArchiveEventHandler
{
    string EventType { get; }
    Task HandleAsync(JsonElement root, byte[] archive);
}

public class BlenderEventDispatcher {
    private readonly Dictionary<string, IBlenderEventHandler> _handlers;
    private readonly Dictionary<string, IBlenderArchiveEventHandler> _archiveHandlers;
    public BlenderEventDispatcher(IEnumerable<IBlenderEventHandler> handlers,
        IEnumerable<IBlenderArchiveEventHandler> archiveHandlers) {
        _handlers = handlers.ToDictionary(h => h.EventType);
        _archiveHandlers = archiveHandlers.ToDictionary(h => h.EventType);
    }

    public void Register(IBlenderEventHandler handler) {
        _handlers.Add(handler.EventType, handler);
    }

    public void Unregister(IBlenderEventHandler handler) {
        _handlers.Remove(handler.EventType);
    }

    public void Dispatch(JsonElement root) {
        if (!root.TryGetProperty("event", out var evtProp))
            return;

        var evt = evtProp.GetString();
        if (evt == null)
            return;

        if (_handlers.TryGetValue(evt, out var handler))
            handler.Handle(root);
        else
            Logger.Warning($"⚠️ Unknown Blender event: {evt}");
    }

    public async Task DispatchArchiveAsync(JsonElement root, byte[] archive)
    {
        if (!root.TryGetProperty("event", out var evtProp))
            return;

        var evt = evtProp.GetString();
        if (evt == null)
            return;

        if (_archiveHandlers.TryGetValue(evt, out var handler))
            await handler.HandleAsync(root, archive);
        else
            Logger.Warning($"⚠️ Unknown Blender archive event: {evt}");
    }
}    