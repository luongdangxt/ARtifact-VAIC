using System;

namespace ARtifact.Core
{
    /// <summary>
    /// Định danh bền vững cho một nghệ nhân di sản.
    /// Dùng chuỗi (vd "ca-tru", "quan-ho") thay vì tham chiếu asset để các module
    /// không phụ thuộc lẫn nhau — chỉ trao đổi qua id này.
    /// </summary>
    [Serializable]
    public readonly struct ArtisanId : IEquatable<ArtisanId>
    {
        public string Value { get; }

        public ArtisanId(string value)
        {
            Value = value;
        }

        public bool IsValid => !string.IsNullOrEmpty(Value);

        public bool Equals(ArtisanId other) => string.Equals(Value, other.Value, StringComparison.Ordinal);
        public override bool Equals(object obj) => obj is ArtisanId other && Equals(other);
        public override int GetHashCode() => Value != null ? Value.GetHashCode() : 0;
        public override string ToString() => Value ?? "<invalid>";

        public static bool operator ==(ArtisanId a, ArtisanId b) => a.Equals(b);
        public static bool operator !=(ArtisanId a, ArtisanId b) => !a.Equals(b);
    }
}
