using System.Collections.Generic;
using ARtifact.Avatar;
using ARtifact.Core;
using UnityEngine;
using UnityEngine.XR.ARSubsystems;

namespace ARtifact.AR
{
    /// <summary>
    /// Chịu trách nhiệm tạo/di chuyển/ẩn-hiện/huỷ model nghệ nhân theo từng marker
    /// (khoá bằng <see cref="TrackableId"/>). Không biết gì về AR session hay tracking —
    /// chỉ nhận lệnh từ <see cref="ImageTrackingService"/>.
    /// </summary>
    public sealed class ArtisanSpawner : MonoBehaviour
    {
        [Tooltip("Node cha chứa các model spawn ra. Bỏ trống = dùng chính transform này.")]
        [SerializeField] private Transform _spawnRoot;

        private Camera _camera;
        private readonly Dictionary<TrackableId, ArtisanView> _active = new();

        public void Initialize(Camera camera)
        {
            _camera = camera;
            if (_spawnRoot == null) _spawnRoot = transform;
        }

        /// <summary>Tạo (nếu chưa có) rồi hiển thị model nghệ nhân tại pose của marker.</summary>
        public ArtisanView Show(TrackableId key, IArtisanDefinition artisan, Pose pose)
        {
            if (!_active.TryGetValue(key, out var view) || view == null)
            {
                if (artisan.Prefab == null)
                {
                    Debug.LogWarning($"[ArtisanSpawner] Nghệ nhân '{artisan.Id}' chưa gán Prefab.");
                    return null;
                }

                var go = Instantiate(artisan.Prefab, pose.position, pose.rotation, _spawnRoot);
                go.name = $"Artisan_{artisan.Id}";

                view = go.GetComponent<ArtisanView>();
                if (view == null) view = go.AddComponent<ArtisanView>();

                view.Bind(artisan, _camera);
                view.PlayIntro();
                _active[key] = view;
            }

            view.transform.SetPositionAndRotation(pose.position, pose.rotation);
            if (!view.gameObject.activeSelf) view.gameObject.SetActive(true);
            return view;
        }

        /// <summary>Cập nhật pose model đang hiển thị theo marker.</summary>
        public void UpdatePose(TrackableId key, Pose pose)
        {
            if (_active.TryGetValue(key, out var view) && view != null)
                view.transform.SetPositionAndRotation(pose.position, pose.rotation);
        }

        /// <summary>Ẩn/hiện model mà không huỷ (khi mất tracking tạm thời).</summary>
        public void SetVisible(TrackableId key, bool visible)
        {
            if (_active.TryGetValue(key, out var view) && view != null &&
                view.gameObject.activeSelf != visible)
            {
                view.gameObject.SetActive(visible);
            }
        }

        /// <summary>Huỷ hẳn model (khi marker bị gỡ khỏi tracking).</summary>
        public void Remove(TrackableId key)
        {
            if (_active.TryGetValue(key, out var view))
            {
                if (view != null) Destroy(view.gameObject);
                _active.Remove(key);
            }
        }
    }
}
