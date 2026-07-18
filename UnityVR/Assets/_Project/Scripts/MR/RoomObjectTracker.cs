using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Events;
using Meta.XR.MRUtilityKit;

namespace ARtifact.MR
{
    /// <summary>
    /// Theo dõi (tracking) các vật thể trong phòng do Meta Scene Understanding phát hiện
    /// thông qua MR Utility Kit (MRUK): tường, sàn, trần, bàn, ghế, cửa, cửa sổ...
    ///
    /// Khi MRUK nạp xong dữ liệu phòng (trên Quest lấy từ Room Setup, trong Editor lấy từ
    /// prefab phòng mẫu), script duyệt toàn bộ anchor của phòng hiện tại: ghi log nhãn +
    /// vị trí và (tuỳ chọn) sinh marker trực quan ôm theo từng vật thể để dễ kiểm tra.
    /// </summary>
    [DisallowMultipleComponent]
    public class RoomObjectTracker : MonoBehaviour
    {
        [Header("Bộ lọc nhãn")]
        [Tooltip("Chỉ theo dõi các nhãn được chọn. Chọn 'Everything' để theo dõi tất cả vật thể.")]
        public MRUKAnchor.SceneLabels labelFilter = (MRUKAnchor.SceneLabels)~0;

        [Header("Marker trực quan")]
        [Tooltip("Bật để sinh marker cho từng vật thể: cube ôm theo khối (bàn, ghế, tủ...), " +
                 "quad theo mặt phẳng (tường, sàn, trần, cửa...).")]
        public bool spawnMarkers = true;

        [Tooltip("Vật liệu dùng cho marker. Bỏ trống sẽ dùng vật liệu mặc định của Unity.")]
        public Material markerMaterial;

        [Header("Sự kiện")]
        [Tooltip("Gọi mỗi khi phòng được tracking xong, kèm số vật thể phát hiện được.")]
        public UnityEvent<int> OnRoomTracked = new UnityEvent<int>();

        private readonly List<GameObject> _spawned = new List<GameObject>();
        private Transform _markerRoot;

        private void Start()
        {
            if (MRUK.Instance == null)
            {
                Debug.LogError("[RoomObjectTracker] Không tìm thấy MRUK trong scene. " +
                               "Hãy thêm prefab 'MRUK' vào scene.");
                return;
            }

            _markerRoot = new GameObject("[Runtime] Room Markers").transform;

            // Đăng ký callback: chạy lại mỗi khi MRUK nạp xong dữ liệu phòng.
            MRUK.Instance.RegisterSceneLoadedCallback(OnSceneLoaded);
            // Cập nhật lại khi phòng thay đổi (người dùng chỉnh Room Setup trong lúc chạy).
            MRUK.Instance.RoomUpdatedEvent.AddListener(OnRoomUpdated);
        }

        private void OnSceneLoaded()
        {
            TrackRoom(MRUK.Instance.GetCurrentRoom());
        }

        private void OnRoomUpdated(MRUKRoom room)
        {
            TrackRoom(room);
        }

        /// <summary>Duyệt toàn bộ anchor của phòng, log và sinh marker.</summary>
        public void TrackRoom(MRUKRoom room)
        {
            ClearMarkers();

            if (room == null)
            {
                Debug.LogWarning("[RoomObjectTracker] Chưa có phòng nào được nạp.");
                OnRoomTracked.Invoke(0);
                return;
            }

            int count = 0;
            var sb = new StringBuilder();
            sb.AppendLine($"[RoomObjectTracker] Phòng '{room.name}' — tổng {room.Anchors.Count} anchor.");

            foreach (var anchor in room.Anchors)
            {
                MRUKAnchor.SceneLabels labels = anchor.GetLabelsAsEnum();
                if ((labels & labelFilter) == 0)
                    continue;

                count++;
                Vector3 pos = anchor.transform.position;
                sb.AppendLine($"  • {labels}  @ ({pos.x:F2}, {pos.y:F2}, {pos.z:F2})");

                if (spawnMarkers)
                    SpawnMarker(anchor, labels);
            }

            sb.AppendLine($"[RoomObjectTracker] Đã tracking {count} vật thể (theo bộ lọc).");
            Debug.Log(sb.ToString());
            OnRoomTracked.Invoke(count);
        }

        private void SpawnMarker(MRUKAnchor anchor, MRUKAnchor.SceneLabels labels)
        {
            GameObject marker;

            if (anchor.VolumeBounds.HasValue)
            {
                // Vật thể dạng khối (bàn, ghế, tủ, giường...) -> cube ôm theo hộp bao.
                Bounds b = anchor.VolumeBounds.Value;
                marker = GameObject.CreatePrimitive(PrimitiveType.Cube);
                marker.transform.SetParent(anchor.transform, false);
                marker.transform.localPosition = b.center;
                marker.transform.localRotation = Quaternion.identity;
                marker.transform.localScale = b.size;
            }
            else if (anchor.PlaneRect.HasValue)
            {
                // Bề mặt phẳng (tường, sàn, trần, cửa, cửa sổ...) -> quad theo kích thước mặt.
                Rect r = anchor.PlaneRect.Value;
                marker = GameObject.CreatePrimitive(PrimitiveType.Quad);
                marker.transform.SetParent(anchor.transform, false);
                marker.transform.localPosition = new Vector3(r.center.x, r.center.y, 0f);
                marker.transform.localRotation = Quaternion.identity;
                marker.transform.localScale = new Vector3(r.width, r.height, 1f);
            }
            else
            {
                // Không có hình học -> chấm nhỏ đánh dấu vị trí anchor.
                marker = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                marker.transform.SetParent(anchor.transform, false);
                marker.transform.localPosition = Vector3.zero;
                marker.transform.localRotation = Quaternion.identity;
                marker.transform.localScale = Vector3.one * 0.1f;
            }

            marker.name = $"Marker_{labels}";

            // Giữ world-transform khi chuyển sang cha gom marker.
            marker.transform.SetParent(_markerRoot, true);

            // Bỏ collider để marker không cản trở raycast/tương tác.
            if (marker.TryGetComponent<Collider>(out var col))
                Destroy(col);

            if (markerMaterial != null && marker.TryGetComponent<MeshRenderer>(out var mr))
                mr.sharedMaterial = markerMaterial;

            _spawned.Add(marker);
        }

        private void ClearMarkers()
        {
            foreach (var go in _spawned)
                if (go != null)
                    Destroy(go);
            _spawned.Clear();
        }

        private void OnDestroy()
        {
            if (MRUK.Instance != null)
                MRUK.Instance.RoomUpdatedEvent.RemoveListener(OnRoomUpdated);
        }
    }
}
