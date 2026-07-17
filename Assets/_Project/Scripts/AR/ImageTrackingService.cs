using System.Collections.Generic;
using ARtifact.Core;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

namespace ARtifact.AR
{
    /// <summary>
    /// Bọc <see cref="ARTrackedImageManager"/>: khi camera nhận diện được ảnh/QR của một
    /// nghệ nhân, tra <see cref="IArtisanCatalog"/> rồi yêu cầu <see cref="ArtisanSpawner"/>
    /// hiện model tương ứng. Phát sự kiện qua <see cref="IEventBus"/> để UI/Conversation
    /// (giai đoạn sau) lắng nghe.
    /// </summary>
    public sealed class ImageTrackingService : MonoBehaviour
    {
        [Tooltip("ARTrackedImageManager (thường nằm trên XR Origin).")]
        [SerializeField] private ARTrackedImageManager _trackedImageManager;

        [Tooltip("Spawner tạo/ẩn model nghệ nhân.")]
        [SerializeField] private ArtisanSpawner _spawner;

        [Tooltip("Ẩn model khi tracking không còn ở trạng thái Tracking (Limited/None).")]
        [SerializeField] private bool _hideWhenNotTracking = true;

        private IArtisanCatalog _catalog;
        private IEventBus _events;

        // Marker đã nhận diện -> nghệ nhân, để phát sự kiện disappeared khi bị gỡ.
        private readonly Dictionary<TrackableId, IArtisanDefinition> _resolved = new();
        // Marker đang hiển thị model, để phát sự kiện đúng một lần mỗi lần đổi trạng thái.
        private readonly HashSet<TrackableId> _visible = new();

        public void Initialize(IArtisanCatalog catalog, IEventBus events, Camera arCamera)
        {
            _catalog = catalog;
            _events = events;
            if (_spawner != null) _spawner.Initialize(arCamera);
        }

        private void OnEnable()
        {
            if (_trackedImageManager != null)
                _trackedImageManager.trackablesChanged.AddListener(OnTrackablesChanged);
        }

        private void OnDisable()
        {
            if (_trackedImageManager != null)
                _trackedImageManager.trackablesChanged.RemoveListener(OnTrackablesChanged);
        }

        private void OnTrackablesChanged(ARTrackablesChangedEventArgs<ARTrackedImage> args)
        {
            foreach (var image in args.added) HandleTracked(image);
            foreach (var image in args.updated) HandleTracked(image);
            foreach (var removed in args.removed) HandleRemoved(removed.Key);
        }

        private void HandleTracked(ARTrackedImage image)
        {
            if (_catalog == null || _spawner == null) return;

            var imageName = image.referenceImage.name;
            if (!_catalog.TryGetByReferenceImage(imageName, out var artisan))
                return; // marker không thuộc catalog — bỏ qua.

            _resolved[image.trackableId] = artisan;

            bool isTracking = image.trackingState == TrackingState.Tracking;
            var pose = new Pose(image.transform.position, image.transform.rotation);

            if (isTracking)
            {
                _spawner.Show(image.trackableId, artisan, pose);
                if (_visible.Add(image.trackableId))
                    _events?.Publish(new ArtisanAppearedEvent(artisan));
            }
            else if (_hideWhenNotTracking)
            {
                _spawner.SetVisible(image.trackableId, false);
                if (_visible.Remove(image.trackableId))
                    _events?.Publish(new ArtisanDisappearedEvent(artisan.Id));
            }
        }

        private void HandleRemoved(TrackableId key)
        {
            _spawner?.Remove(key);

            if (_resolved.TryGetValue(key, out var artisan))
            {
                if (_visible.Remove(key))
                    _events?.Publish(new ArtisanDisappearedEvent(artisan.Id));
                _resolved.Remove(key);
            }
        }
    }
}
