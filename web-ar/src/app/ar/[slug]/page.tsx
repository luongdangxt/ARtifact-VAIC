import { notFound } from 'next/navigation';
import { getArtisanBySlug, artisans } from '@/data/artisans';
import ARSceneClient from '@/features/ar/ARSceneClient';

// Sinh sẵn các route tĩnh cho từng nghệ nhân.
export function generateStaticParams() {
  return artisans.map((a) => ({ slug: a.slug }));
}

export default async function ARPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const artisan = getArtisanBySlug(slug);
  if (!artisan) notFound();

  return <ARSceneClient artisan={artisan} />;
}
