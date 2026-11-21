namespace SeeSharp.Blender;

public class PathViewerClient {
    public readonly CreatedHandler _created;
    public readonly DeletedHandler _deleted;
    public readonly SelectedHandler _selected;
    public readonly AssetsRequestHandler _assetsRequested;
    public readonly FullSceneRequestHandler _fullSceneRequested;

    public PathViewerClient(IEnumerable<IBlenderEventHandler> handlers) {
        _created = handlers
            .OfType<CreatedHandler>()
            .Single(); 
        _deleted = handlers
            .OfType<DeletedHandler>()
            .Single(); 
        _selected = handlers
            .OfType<SelectedHandler>()
            .Single();
        _assetsRequested = handlers
            .OfType<AssetsRequestHandler>()
            .Single();
        _fullSceneRequested = handlers
            .OfType<FullSceneRequestHandler>()
            .Single();
    } 
}    