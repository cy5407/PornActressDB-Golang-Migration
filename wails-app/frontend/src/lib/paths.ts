/**
 * Return the basename (final path segment) of a Windows-style or POSIX path.
 * 分類搬移 destination 必須沿用來源 basename，避免 multi-part 同 code 不同
 * basename 被壓成同一目標（例如 KUSE-042-1.mp4 / KUSE-042-2.mp4）。
 */
export function basenameOf(path: string): string {
  if (!path) return '';
  const normalized = path.replace(/\//g, '\\');
  return normalized.split('\\').pop() || path;
}
