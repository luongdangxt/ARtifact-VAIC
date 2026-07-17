import Link from "next/link";
import { artisans } from "@/data/artisans";

// Landing: danh sách nghệ nhân.
// Server Component đọc thẳng tầng data (nguồn dữ liệu duy nhất, cũng là nguồn của /api/artisans).
// Client Component / GĐ2 dùng lib/api-client (HTTP). Đổi nguồn -> sửa data + api-client + route.
export default function Home() {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-12">
      <header className="mb-8">
        <h1 className="text-3xl font-bold">ARtifact VAIC</h1>
        <p className="mt-2 text-black/60 dark:text-white/60">
          Web AR nghệ nhân di sản — quét ảnh mốc để hiện model 3D. Không cần cài app.
        </p>
      </header>

      {/* Hướng dẫn cách hoạt động — AR image-tracking cần chĩa camera vào ảnh mốc */}
      <div className="mb-8 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm">
        <p className="font-semibold">Cách trải nghiệm (quan trọng):</p>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-black/70 dark:text-white/70">
          <li>Đây là AR <b>quét ảnh mốc</b>: bạn phải <b>chĩa camera vào một tấm ảnh mốc</b> thì model 3D mới hiện.</li>
          <li>
            Mở <a href="/markers/sample-card.png" target="_blank" className="font-medium text-blue-600 underline dark:text-blue-400">ảnh mốc mẫu ↗</a>{" "}
            rồi <b>in ra giấy</b> hoặc <b>hiện trên một màn hình khác</b> (vd màn máy tính).
          </li>
          <li>Trên <b>điện thoại</b> (đang mở trang này qua HTTPS), bấm một nghệ nhân → “Bắt đầu quét AR” → cho phép camera → chĩa vào ảnh mốc đó.</li>
        </ol>
        <p className="mt-2 text-xs text-black/50 dark:text-white/50">
          Lưu ý: chỉ mở trang trên một máy tính rồi bấm sẽ không thấy gì, vì không có ảnh mốc để camera quét.
        </p>
      </div>

      <section className="grid gap-4">
        {artisans.map((a) => (
          <Link
            key={a.slug}
            href={`/ar/${a.slug}`}
            className="rounded-2xl border border-black/10 p-5 transition hover:border-black/30 dark:border-white/15 dark:hover:border-white/40"
          >
            <h2 className="text-lg font-semibold">{a.name}</h2>
            <p className="text-sm text-black/60 dark:text-white/60">{a.craft}</p>
            <p className="mt-2 line-clamp-2 text-sm text-black/50 dark:text-white/50">
              {a.bio}
            </p>
            <span className="mt-3 inline-block text-sm font-medium text-blue-600 dark:text-blue-400">
              Mở AR →
            </span>
          </Link>
        ))}
      </section>

      <footer className="mt-12 text-xs text-black/40 dark:text-white/40">
        Mở trên điện thoại (HTTPS) và cho phép quyền camera để trải nghiệm AR.
      </footer>
    </main>
  );
}
