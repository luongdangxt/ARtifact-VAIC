using System.Collections.Generic;

namespace ARtifact.Core
{
    /// <summary>
    /// Kho tra cứu nghệ nhân. Cài đặt cụ thể (ScriptableObject) nằm ở module Heritage,
    /// nhưng module AR chỉ làm việc qua interface này.
    /// </summary>
    public interface IArtisanCatalog
    {
        IReadOnlyList<IArtisanDefinition> All { get; }

        /// <summary>Tra nghệ nhân theo tên reference image (marker) đã nhận diện.</summary>
        bool TryGetByReferenceImage(string referenceImageName, out IArtisanDefinition artisan);

        /// <summary>Tra nghệ nhân theo định danh.</summary>
        bool TryGetById(ArtisanId id, out IArtisanDefinition artisan);
    }
}
