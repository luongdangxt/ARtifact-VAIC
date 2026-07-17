using ARtifact.Core;
using UnityEngine;

namespace ARtifact.UI
{
    /// <summary>
    /// Khung UI cho giai đoạn sau: hiện tên/mô tả nghệ nhân và (về sau) ô chat.
    /// Giai đoạn 1 chỉ là chỗ giữ chỗ, lắng nghe sự kiện xuất hiện/biến mất qua event bus.
    /// </summary>
    public sealed class ArtisanInfoPanel : MonoBehaviour
    {
        private IEventBus _events;

        /// <summary>Gọi từ AppBootstrap ở giai đoạn sau để nối event bus vào UI.</summary>
        public void Initialize(IEventBus events)
        {
            _events = events;
            _events?.Subscribe<ArtisanAppearedEvent>(OnArtisanAppeared);
            _events?.Subscribe<ArtisanDisappearedEvent>(OnArtisanDisappeared);
        }

        private void OnDestroy()
        {
            _events?.Unsubscribe<ArtisanAppearedEvent>(OnArtisanAppeared);
            _events?.Unsubscribe<ArtisanDisappearedEvent>(OnArtisanDisappeared);
        }

        private void OnArtisanAppeared(ArtisanAppearedEvent e)
        {
            // TODO (giai đoạn sau): hiển thị panel với e.Artisan.DisplayName / Description.
            Debug.Log($"[UI] Nghệ nhân xuất hiện: {e.Artisan.DisplayName}");
        }

        private void OnArtisanDisappeared(ArtisanDisappearedEvent e)
        {
            // TODO (giai đoạn sau): ẩn panel.
            Debug.Log($"[UI] Nghệ nhân biến mất: {e.Id}");
        }
    }
}
