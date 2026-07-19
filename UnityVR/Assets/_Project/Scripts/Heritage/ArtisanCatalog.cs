using System.Collections.Generic;
using ARtifact.Core;
using UnityEngine;

namespace ARtifact.Heritage
{
    /// <summary>
    /// Danh mục tất cả nghệ nhân của app (asset ScriptableObject). Cài đặt
    /// <see cref="IArtisanCatalog"/> để module AR tra cứu qua interface.
    /// </summary>
    [CreateAssetMenu(
        fileName = "ArtisanCatalog",
        menuName = "ARtifact/Artisan Catalog",
        order = 1)]
    public sealed class ArtisanCatalog : ScriptableObject, IArtisanCatalog
    {
        [Tooltip("Danh sách nghệ nhân. Kéo các asset HeritageArtisan vào đây.")]
        [SerializeField] private List<HeritageArtisan> _artisans = new();

        private Dictionary<string, IArtisanDefinition> _byImage;
        private Dictionary<string, IArtisanDefinition> _byId;

        public IReadOnlyList<IArtisanDefinition> All
        {
            get
            {
                EnsureIndex();
                return _artisans;
            }
        }

        public bool TryGetByReferenceImage(string referenceImageName, out IArtisanDefinition artisan)
        {
            EnsureIndex();
            return _byImage.TryGetValue(referenceImageName ?? string.Empty, out artisan);
        }

        public bool TryGetById(ArtisanId id, out IArtisanDefinition artisan)
        {
            EnsureIndex();
            return _byId.TryGetValue(id.Value ?? string.Empty, out artisan);
        }

        private void OnEnable()
        {
            // Reset index khi asset được nạp lại (thay đổi trong Editor).
            _byImage = null;
            _byId = null;
        }

        private void EnsureIndex()
        {
            if (_byImage != null && _byId != null) return;

            _byImage = new Dictionary<string, IArtisanDefinition>();
            _byId = new Dictionary<string, IArtisanDefinition>();

            foreach (var artisan in _artisans)
            {
                if (artisan == null) continue;

                var imageName = artisan.ReferenceImageName;
                if (!string.IsNullOrEmpty(imageName))
                {
                    if (_byImage.ContainsKey(imageName))
                        Debug.LogWarning($"[ArtisanCatalog] Trùng reference image '{imageName}'.", this);
                    else
                        _byImage[imageName] = artisan;
                }

                var idValue = artisan.Id.Value;
                if (!string.IsNullOrEmpty(idValue))
                {
                    if (_byId.ContainsKey(idValue))
                        Debug.LogWarning($"[ArtisanCatalog] Trùng id '{idValue}'.", this);
                    else
                        _byId[idValue] = artisan;
                }
            }
        }
    }
}
