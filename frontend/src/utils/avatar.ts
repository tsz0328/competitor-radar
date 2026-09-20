/**
 * 头像占位算法（顶栏 / 侧边栏共用，避免两处各写一份导致风格漂移）。
 *
 * 有 avatar（data URL）就直接显示图片；没有则用「名字首字母 + 由名字哈希出的稳定底色」。
 */

/** 名字首字母（空名字用 ? 兜底） */
export function avatarInitials(name?: string | null): string {
  return (name?.trim()?.[0] ?? "?").toUpperCase();
}

/** 由名字算出的稳定底色：同一个名字永远同一个颜色 */
export function avatarColor(name?: string | null): string {
  const text = name || "";
  let h = 0;
  for (let i = 0; i < text.length; i++) h = text.charCodeAt(i) + ((h << 5) - h);
  return `hsl(${Math.abs(h) % 360}, 60%, 55%)`;
}
