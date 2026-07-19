using ARtifact.Core;
using UnityEngine;

namespace ARtifact.Avatar
{
    /// <summary>
    /// Component gắn trên prefab model nghệ nhân. Giai đoạn 1: chạy idle animation và
    /// (tuỳ chọn) quay mặt về camera. Đã chừa sẵn API cho lip-sync/TTS ở giai đoạn sau.
    /// </summary>
    public sealed class ArtisanView : MonoBehaviour
    {
        [Header("Animation (tuỳ chọn)")]
        [Tooltip("Animator của model. Bỏ trống nếu model chưa có animation.")]
        [SerializeField] private Animator _animator;

        [Tooltip("Trigger phát animation chào/giới thiệu.")]
        [SerializeField] private string _introTrigger = "Intro";

        [Tooltip("Bool bật/tắt trạng thái đang nói (dành cho TTS/lip-sync sau này).")]
        [SerializeField] private string _speakingBool = "IsSpeaking";

        [Header("Hướng nhìn")]
        [Tooltip("Nếu bật, model tự quay mặt về camera quanh trục Y (billboard mềm).")]
        [SerializeField] private bool _faceCamera = true;

        private Camera _target;
        private ArtisanId _boundId;

        /// <summary>Id của nghệ nhân đang được model này thể hiện.</summary>
        public ArtisanId BoundId => _boundId;

        /// <summary>Gắn dữ liệu nghệ nhân và camera mục tiêu (gọi khi spawn).</summary>
        public void Bind(IArtisanDefinition artisan, Camera target)
        {
            _boundId = artisan != null ? artisan.Id : default;
            _target = target;
        }

        /// <summary>Phát animation chào/giới thiệu.</summary>
        public void PlayIntro()
        {
            if (_animator != null && !string.IsNullOrEmpty(_introTrigger))
                _animator.SetTrigger(_introTrigger);
        }

        /// <summary>Bật/tắt trạng thái đang nói — dùng cho lip-sync khi tích hợp TTS.</summary>
        public void SetSpeaking(bool speaking)
        {
            if (_animator != null && !string.IsNullOrEmpty(_speakingBool))
                _animator.SetBool(_speakingBool, speaking);
        }

        private void LateUpdate()
        {
            if (!_faceCamera || _target == null) return;

            var toCamera = _target.transform.position - transform.position;
            toCamera.y = 0f;
            if (toCamera.sqrMagnitude < 0.0001f) return;

            transform.rotation = Quaternion.LookRotation(toCamera);
        }
    }
}
