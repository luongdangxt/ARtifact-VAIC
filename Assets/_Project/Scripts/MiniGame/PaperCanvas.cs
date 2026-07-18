using UnityEngine;

namespace ARtifact.MiniGame
{
    /// <summary>
    /// Tờ giấy trắng có thể vẽ lên. Sở hữu một <see cref="RenderTexture"/> làm mặt giấy;
    /// đầu bút "chấm mực" bằng cách stamp các đốm mực mềm vào RT (mực loang trên giấy).
    /// Gắn trên quad giấy; quad cần có Renderer (material URP/Unlit) và MeshCollider để
    /// <see cref="BrushPainter"/> raycast lấy toạ độ UV.
    /// </summary>
    [RequireComponent(typeof(Renderer))]
    public sealed class PaperCanvas : MonoBehaviour
    {
        [Header("Kích thước & màu")]
        [Tooltip("Độ phân giải RenderTexture của mặt giấy (vuông).")]
        [SerializeField] private int _resolution = 1024;
        [Tooltip("Màu nền giấy khi chưa vẽ / sau khi xoá.")]
        [SerializeField] private Color _paperColor = new Color(0.97f, 0.95f, 0.90f, 1f);
        [Tooltip("Màu mực.")]
        [SerializeField] private Color _inkColor = new Color(0.09f, 0.07f, 0.06f, 1f);

        [Header("Cọ")]
        [Tooltip("Bán kính đốm mực tính theo tỉ lệ chiều rộng giấy (0..1).")]
        [Range(0.005f, 0.15f)]
        [SerializeField] private float _brushSizeUV = 0.03f;
        [Tooltip("Độ mờ mềm của mép vết mực (0 = cứng, 1 = rất mờ).")]
        [Range(0f, 1f)]
        [SerializeField] private float _brushSoftness = 0.5f;

        [Header("Shader")]
        [Tooltip("Shader 'ARtifact/InkStamp' dùng để stamp mực vào RT.")]
        [SerializeField] private Shader _inkShader;

        [Tooltip("Tên property texture chính trên material giấy (URP/Unlit = _BaseMap).")]
        [SerializeField] private string _paperTextureProperty = "_BaseMap";

        private RenderTexture _rt;
        private Texture2D _stamp;
        private Material _inkMaterial;
        private MaterialPropertyBlock _mpb;
        private Renderer _renderer;
        private int _paperTexId;

        /// <summary>Kích thước cọ mặc định (tỉ lệ UV).</summary>
        public float BrushSizeUV => _brushSizeUV;

        private void Awake()
        {
            _renderer = GetComponent<Renderer>();
            _paperTexId = Shader.PropertyToID(_paperTextureProperty);

            _rt = new RenderTexture(_resolution, _resolution, 0, RenderTextureFormat.ARGB32)
            {
                name = "PaperCanvasRT",
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear
            };
            _rt.Create();

            _stamp = BuildStampTexture(128, _brushSoftness);

            if (_inkShader == null) _inkShader = Shader.Find("ARtifact/InkStamp");
            _inkMaterial = new Material(_inkShader);
            _inkMaterial.SetColor("_Color", _inkColor);
            _inkMaterial.mainTexture = _stamp;

            _mpb = new MaterialPropertyBlock();
            _renderer.GetPropertyBlock(_mpb);
            _mpb.SetTexture(_paperTexId, _rt);
            _renderer.SetPropertyBlock(_mpb);

            Clear();
        }

        private void OnDestroy()
        {
            if (_rt != null) _rt.Release();
            if (_inkMaterial != null) Destroy(_inkMaterial);
            if (_stamp != null) Destroy(_stamp);
        }

        /// <summary>Xoá sạch giấy về màu nền.</summary>
        public void Clear()
        {
            var prev = RenderTexture.active;
            RenderTexture.active = _rt;
            GL.Clear(true, true, _paperColor);
            RenderTexture.active = prev;
        }

        /// <summary>Chấm một đốm mực tại toạ độ UV (0..1) với kích thước UV cho trước.</summary>
        public void PaintDab(Vector2 uv, float sizeUV)
        {
            if (_rt == null) return;

            var prev = RenderTexture.active;
            RenderTexture.active = _rt;
            GL.PushMatrix();
            // Toạ độ pixel, gốc ở góc trên-trái (y hướng xuống).
            GL.LoadPixelMatrix(0, _rt.width, _rt.height, 0);

            float px = uv.x * _rt.width;
            float py = (1f - uv.y) * _rt.height;
            float s = Mathf.Max(1f, sizeUV * _rt.width);
            var r = new Rect(px - s * 0.5f, py - s * 0.5f, s, s);
            Graphics.DrawTexture(r, _stamp, _inkMaterial);

            GL.PopMatrix();
            RenderTexture.active = prev;
        }

        /// <summary>Chấm mực mặc định.</summary>
        public void PaintDab(Vector2 uv) => PaintDab(uv, _brushSizeUV);

        /// <summary>
        /// Vẽ một đoạn nét liền từ <paramref name="uvFrom"/> tới <paramref name="uvTo"/>
        /// bằng cách nội suy nhiều đốm mực để nét không bị đứt quãng.
        /// </summary>
        public void PaintStroke(Vector2 uvFrom, Vector2 uvTo, float sizeUV)
        {
            float dist = Vector2.Distance(uvFrom, uvTo);
            float step = Mathf.Max(sizeUV * 0.35f, 0.002f);
            int count = Mathf.CeilToInt(dist / step);
            if (count <= 1)
            {
                PaintDab(uvTo, sizeUV);
                return;
            }
            for (int i = 1; i <= count; i++)
            {
                PaintDab(Vector2.Lerp(uvFrom, uvTo, i / (float)count), sizeUV);
            }
        }

        /// <summary>Vẽ đoạn nét với kích thước cọ mặc định.</summary>
        public void PaintStroke(Vector2 uvFrom, Vector2 uvTo) => PaintStroke(uvFrom, uvTo, _brushSizeUV);

        /// <summary>Sinh texture đốm mực tròn, alpha giảm dần ra mép (mềm).</summary>
        private static Texture2D BuildStampTexture(int size, float softness)
        {
            var tex = new Texture2D(size, size, TextureFormat.RGBA32, false)
            {
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear
            };
            float half = size * 0.5f;
            // softness 0 => mép cứng, 1 => tan gần hết. inner là bán kính bắt đầu tan.
            float inner = Mathf.Lerp(0.95f, 0.05f, Mathf.Clamp01(softness));
            var pixels = new Color[size * size];
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float dx = (x + 0.5f - half) / half;
                    float dy = (y + 0.5f - half) / half;
                    float d = Mathf.Sqrt(dx * dx + dy * dy); // 0 tâm, 1 mép
                    float a = 1f - Mathf.SmoothStep(inner, 1f, d);
                    pixels[y * size + x] = new Color(1f, 1f, 1f, a);
                }
            }
            tex.SetPixels(pixels);
            tex.Apply();
            return tex;
        }
    }
}
