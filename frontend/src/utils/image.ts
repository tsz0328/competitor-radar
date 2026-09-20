/**
 * 图片处理小工具（当前用于「用户中心」的头像上传）。
 */

/**
 * 把用户选的图片居中裁成正方形并压缩成 data URL。
 *
 * 为什么在前端裁/压：项目没有静态文件服务，头像直接以 data URL 存库、
 * 并随登录响应下发，所以必须足够小（默认 160×160 JPEG，约 5~10KB）。
 */
export function fileToSquareDataUrl(file: File, size = 160): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error("请选择图片文件"));
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(objectUrl);
      const ctx = document.createElement("canvas").getContext("2d");
      if (!ctx) {
        reject(new Error("当前浏览器不支持图片处理"));
        return;
      }
      const canvas = ctx.canvas;
      canvas.width = size;
      canvas.height = size;
      // 居中裁剪：短边铺满，避免头像被拉变形
      const side = Math.min(img.width, img.height);
      ctx.drawImage(
        img,
        (img.width - side) / 2,
        (img.height - side) / 2,
        side,
        side,
        0,
        0,
        size,
        size,
      );
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("图片读取失败"));
    };
    img.src = objectUrl;
  });
}
