using System.Collections;
using ARtifact.Core;
using UnityEngine;

namespace ARtifact.MiniGame
{
    /// <summary>
    /// Bộ điều khiển mini-game "vẽ tranh Đông Hồ": đếm số nét vẽ trên <see cref="PaperCanvas"/>,
    /// khi đủ <see cref="_requiredStrokes"/> nét thì hé lộ ngẫu nhiên một bức tranh (fade-in
    /// quad tranh đè lên giấy) và phát sự kiện qua <see cref="IEventBus"/>.
    /// </summary>
    public sealed class MiniGameController : MonoBehaviour
    {
        [Header("Tham chiếu")]
        [SerializeField] private PaperCanvas _paperCanvas;
        [Tooltip("Renderer của quad tranh hiển thị, đè khít lên giấy (ẩn lúc đầu).")]
        [SerializeField] private Renderer _paintingDisplay;

        [Header("Tranh Đông Hồ (URP/Unlit, Surface=Transparent)")]
        [Tooltip("Danh sách material tranh; khi đủ nét sẽ chọn ngẫu nhiên 1 để hiện.")]
        [SerializeField] private Material[] _paintingMaterials;

        [Header("Luật chơi")]
        [Tooltip("Số nét cần vẽ để hé lộ tranh.")]
        [SerializeField] private int _requiredStrokes = 5;
        [Tooltip("Thời gian fade-in tranh (giây).")]
        [SerializeField] private float _fadeDuration = 1.0f;
        [Tooltip("Tên property màu trên material tranh để fade alpha (URP = _BaseColor).")]
        [SerializeField] private string _colorProperty = "_BaseColor";

        private IEventBus _events;
        private int _strokeCount;
        private bool _revealed;
        private Coroutine _fadeRoutine;
        private int _colorId;

        /// <summary>Tờ giấy mà <see cref="BrushPainter"/> vẽ lên.</summary>
        public PaperCanvas Canvas => _paperCanvas;

        /// <summary>Số nét đã vẽ.</summary>
        public int StrokeCount => _strokeCount;

        private void Awake()
        {
            _colorId = Shader.PropertyToID(_colorProperty);
            ResetGame();
        }

        /// <summary>Nối event bus (gọi từ AppBootstrap). Có thể bỏ qua nếu chạy độc lập.</summary>
        public void Initialize(IEventBus events) => _events = events;

        /// <summary>Được <see cref="BrushPainter"/> gọi khi hoàn tất một nét.</summary>
        public void NotifyStrokeCompleted()
        {
            if (_revealed) return;

            _strokeCount++;
            _events?.Publish(new StrokeCompletedEvent(_strokeCount));

            if (_strokeCount >= _requiredStrokes)
                RevealRandomPainting();
        }

        /// <summary>Hé lộ ngẫu nhiên một bức tranh.</summary>
        public void RevealRandomPainting()
        {
            if (_revealed || _paintingMaterials == null || _paintingMaterials.Length == 0) return;
            _revealed = true;

            int idx = Random.Range(0, _paintingMaterials.Length);
            if (_paintingDisplay != null)
            {
                _paintingDisplay.enabled = true;
                _paintingDisplay.material = _paintingMaterials[idx];
                if (_fadeRoutine != null) StopCoroutine(_fadeRoutine);
                _fadeRoutine = StartCoroutine(FadeIn(_paintingDisplay.material));
            }

            _events?.Publish(new PaintingRevealedEvent(idx));
        }

        /// <summary>Xoá giấy, ẩn tranh, đặt lại bộ đếm để chơi lại.</summary>
        public void ResetGame()
        {
            if (_fadeRoutine != null) { StopCoroutine(_fadeRoutine); _fadeRoutine = null; }
            _strokeCount = 0;
            _revealed = false;

            if (_paperCanvas != null) _paperCanvas.Clear();
            if (_paintingDisplay != null) _paintingDisplay.enabled = false;
        }

        private IEnumerator FadeIn(Material mat)
        {
            SetAlpha(mat, 0f);
            float t = 0f;
            while (t < _fadeDuration)
            {
                t += Time.deltaTime;
                SetAlpha(mat, Mathf.Clamp01(t / _fadeDuration));
                yield return null;
            }
            SetAlpha(mat, 1f);
            _fadeRoutine = null;
        }

        private void SetAlpha(Material mat, float a)
        {
            if (mat == null) return;
            if (mat.HasProperty(_colorId))
            {
                var c = mat.GetColor(_colorId);
                c.a = a;
                mat.SetColor(_colorId, c);
            }
            else
            {
                var c = mat.color;
                c.a = a;
                mat.color = c;
            }
        }
    }
}
