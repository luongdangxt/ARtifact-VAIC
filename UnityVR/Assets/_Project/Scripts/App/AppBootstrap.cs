using ARtifact.AR;
using ARtifact.Conversation;
using ARtifact.Core;
using ARtifact.Heritage;
using UnityEngine;

namespace ARtifact.App
{
    /// <summary>
    /// Composition root duy nhất của app: tạo các dịch vụ chung (event bus, hội thoại) và
    /// nối chúng vào các service AR. Đây là nơi duy nhất "biết" tất cả module — các module
    /// khác không tham chiếu chéo nhau.
    /// </summary>
    public sealed class AppBootstrap : MonoBehaviour
    {
        [Header("Dữ liệu")]
        [SerializeField] private ArtisanCatalog _catalog;

        [Header("AR")]
        [SerializeField] private ARSessionController _sessionController;
        [SerializeField] private ImageTrackingService _imageTrackingService;
        [Tooltip("Camera AR. Bỏ trống = tự lấy Camera.main.")]
        [SerializeField] private Camera _arCamera;

        // Dịch vụ dùng chung — mở public để giai đoạn sau (UI, hội thoại) lấy dùng.
        public IEventBus Events { get; private set; }
        public IConversationService Conversation { get; private set; }
        public IArtisanCatalog Catalog => _catalog;

        private void Awake()
        {
            Events = new EventBus();
            Conversation = new ConversationService(new OfflineLLMClient());

            if (_arCamera == null) _arCamera = Camera.main;

            if (_catalog == null)
                Debug.LogError("[AppBootstrap] Chưa gán ArtisanCatalog.", this);

            if (_imageTrackingService != null)
                _imageTrackingService.Initialize(_catalog, Events, _arCamera);
            else
                Debug.LogError("[AppBootstrap] Chưa gán ImageTrackingService.", this);
        }
    }
}
