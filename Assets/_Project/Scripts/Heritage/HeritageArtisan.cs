using ARtifact.Core;
using UnityEngine;

namespace ARtifact.Heritage
{
    /// <summary>
    /// Dữ liệu một nghệ nhân di sản văn hóa phi vật thể (asset ScriptableObject).
    /// Liên kết một reference image (marker) với model humanoid sẽ hiện ra trong AR.
    /// </summary>
    [CreateAssetMenu(
        fileName = "Artisan_",
        menuName = "ARtifact/Heritage Artisan",
        order = 0)]
    public sealed class HeritageArtisan : ScriptableObject, IArtisanDefinition
    {
        [Header("Định danh")]
        [Tooltip("Id bền vững, không dấu, dạng kebab-case. Vd: ca-tru, quan-ho.")]
        [SerializeField] private string _id = "ca-tru";

        [Tooltip("Tên hiển thị cho người dùng.")]
        [SerializeField] private string _displayName = "Nghệ nhân Ca trù";

        [Header("Nhận diện AR")]
        [Tooltip("Tên reference image trong XRReferenceImageLibrary. Phải TRÙNG tên marker.")]
        [SerializeField] private string _referenceImageName = "ca-tru-marker";

        [Tooltip("Prefab model humanoid sẽ spawn trên marker.")]
        [SerializeField] private GameObject _prefab;

        [Header("Nội dung di sản")]
        [Tooltip("Mô tả ngắn — dùng cho UI và làm ngữ cảnh cho AI ở giai đoạn sau.")]
        [TextArea(3, 8)]
        [SerializeField] private string _description = "";

        public ArtisanId Id => new ArtisanId(_id);
        public string DisplayName => _displayName;
        public string ReferenceImageName => _referenceImageName;
        public GameObject Prefab => _prefab;
        public string Description => _description;
    }
}
