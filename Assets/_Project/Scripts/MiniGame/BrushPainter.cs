using UnityEngine;

namespace ARtifact.MiniGame
{
    /// <summary>
    /// Gắn trên prefab bút lông. Mỗi frame bắn một tia ngắn từ đầu ngọn bút; khi tia chạm
    /// mặt <see cref="PaperCanvas"/> thì "chấm mực" theo toạ độ UV. Một lần hạ bút → nhấc bút
    /// (có ân hạn nhỏ để lọc rung) được tính là một nét và báo về <see cref="MiniGameController"/>.
    /// Painter thuần physics/raycast, không phụ thuộc Interaction SDK — việc cầm-thả bút do
    /// component grab của Meta lo. Có thể tắt vẽ khi thả bút bằng cách gọi <see cref="SetPaintingEnabled"/>
    /// từ UnityEvent của Grabbable trong Inspector.
    /// </summary>
    public sealed class BrushPainter : MonoBehaviour
    {
        [Header("Tham chiếu")]
        [Tooltip("Empty transform đặt đúng đầu ngọn bút. Trục +Z (forward) hướng ra đầu bút.")]
        [SerializeField] private Transform _brushTip;
        [Tooltip("Bộ điều khiển mini-game (đối tượng trong scene).")]
        [SerializeField] private MiniGameController _controller;

        [Header("Chạm giấy")]
        [Tooltip("Độ dài tia dò từ đầu bút (m). Xem như khoảng cách 'chạm' giấy.")]
        [SerializeField] private float _rayLength = 0.02f;
        [Tooltip("Layer của tờ giấy. Để Everything nếu không set layer riêng.")]
        [SerializeField] private LayerMask _paperMask = ~0;
        [Tooltip("Thời gian ân hạn khi mất tiếp xúc trước khi coi là kết thúc nét (giây).")]
        [SerializeField] private float _liftGrace = 0.12f;

        private bool _drawing;
        private Vector2 _lastUv;
        private float _liftTimer;
        private bool _paintingEnabled = true;

        /// <summary>Bật/tắt khả năng vẽ (gọi từ sự kiện grab: cầm = true, thả = false).</summary>
        public void SetPaintingEnabled(bool enabled)
        {
            _paintingEnabled = enabled;
            if (!enabled) EndStrokeIfDrawing();
        }

        private void Reset()
        {
            _brushTip = transform;
        }

        private void Update()
        {
            if (_controller == null || _brushTip == null) return;

            bool hitPaper = false;
            Vector2 uv = default;

            if (_paintingEnabled &&
                Physics.Raycast(_brushTip.position, _brushTip.forward, out var hit,
                                _rayLength, _paperMask, QueryTriggerInteraction.Collide))
            {
                var canvas = hit.collider.GetComponent<PaperCanvas>();
                if (canvas != null && canvas == _controller.Canvas)
                {
                    hitPaper = true;
                    uv = hit.textureCoord; // cần MeshCollider trên quad giấy
                }
            }

            if (hitPaper)
            {
                _liftTimer = 0f;
                if (!_drawing)
                {
                    _drawing = true;
                    _lastUv = uv;
                    _controller.Canvas.PaintDab(uv);
                }
                else
                {
                    _controller.Canvas.PaintStroke(_lastUv, uv);
                    _lastUv = uv;
                }
            }
            else if (_drawing)
            {
                // Ân hạn: chỉ kết thúc nét sau khi rời giấy đủ lâu (lọc rung/nảy).
                _liftTimer += Time.deltaTime;
                if (_liftTimer >= _liftGrace) EndStrokeIfDrawing();
            }
        }

        private void EndStrokeIfDrawing()
        {
            if (!_drawing) return;
            _drawing = false;
            _liftTimer = 0f;
            _controller.NotifyStrokeCompleted();
        }

        private void OnDrawGizmosSelected()
        {
            if (_brushTip == null) return;
            Gizmos.color = Color.cyan;
            Gizmos.DrawLine(_brushTip.position, _brushTip.position + _brushTip.forward * _rayLength);
        }
    }
}
