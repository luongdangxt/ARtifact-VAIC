using System.Collections;
using UnityEngine;
using UnityEngine.XR.ARFoundation;

namespace ARtifact.AR
{
    /// <summary>
    /// Quản lý vòng đời <see cref="ARSession"/>: kiểm tra thiết bị có hỗ trợ AR không,
    /// bật/tắt và reset session.
    /// </summary>
    public sealed class ARSessionController : MonoBehaviour
    {
        [SerializeField] private ARSession _session;

        public ARSession Session => _session;
        public bool IsSupported => ARSession.state != ARSessionState.Unsupported;

        private IEnumerator Start()
        {
            if (_session == null) _session = FindAnyObjectByType<ARSession>();

            if (ARSession.state == ARSessionState.None ||
                ARSession.state == ARSessionState.CheckingAvailability)
            {
                yield return ARSession.CheckAvailability();
            }

            if (ARSession.state == ARSessionState.Unsupported)
                Debug.LogError("[ARSessionController] Thiết bị không hỗ trợ AR (ARCore).");
        }

        public void SetSessionEnabled(bool value)
        {
            if (_session != null) _session.enabled = value;
        }

        /// <summary>Reset session — xoá toàn bộ trackable và bắt đầu lại.</summary>
        public void RestartSession()
        {
            if (_session != null) _session.Reset();
        }
    }
}
