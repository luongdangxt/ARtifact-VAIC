using UnityEngine;

namespace ARtifact.MiniGame
{
    /// <summary>
    /// Đọc nút trên tay cầm Meta Quest để reset mini-game (chơi lại). Tách riêng khỏi
    /// <see cref="MiniGameController"/> để controller không phụ thuộc trực tiếp vào OVRInput.
    /// </summary>
    public sealed class MiniGameInput : MonoBehaviour
    {
        [SerializeField] private MiniGameController _controller;
        [Tooltip("Nút reset (mặc định B trên tay phải).")]
        [SerializeField] private OVRInput.Button _resetButton = OVRInput.Button.Two;

        private void Update()
        {
            if (_controller == null) return;
            if (OVRInput.GetDown(_resetButton))
                _controller.ResetGame();
        }
    }
}
