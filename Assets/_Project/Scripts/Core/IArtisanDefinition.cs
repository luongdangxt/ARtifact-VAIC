using UnityEngine;

namespace ARtifact.Core
{
    /// <summary>
    /// Hợp đồng dữ liệu của một nghệ nhân mà các module khác (AR, UI, Conversation)
    /// tiêu thụ. Định nghĩa cụ thể nằm ở module Heritage; các module khác chỉ biết
    /// interface này để không phụ thuộc vào Heritage.
    /// </summary>
    public interface IArtisanDefinition
    {
        ArtisanId Id { get; }

        /// <summary>Tên hiển thị, vd "Nghệ nhân Ca trù".</summary>
        string DisplayName { get; }

        /// <summary>
        /// Tên của reference image trong XRReferenceImageLibrary dùng để nhận diện
        /// nghệ nhân này. Phải trùng với tên ảnh/marker trong thư viện.
        /// </summary>
        string ReferenceImageName { get; }

        /// <summary>Prefab model humanoid sẽ được spawn khi nhận diện được marker.</summary>
        GameObject Prefab { get; }

        /// <summary>Mô tả ngắn về di sản/nghề (dùng cho UI, context cho AI sau này).</summary>
        string Description { get; }
    }
}
