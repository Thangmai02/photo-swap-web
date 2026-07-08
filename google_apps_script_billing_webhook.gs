/**
 * GOOGLE APPS SCRIPT — Nhận log thanh toán từ nhiều máy, ghi vào 1 Google Sheet.
 *
 * CÁCH DÙNG:
 * 1. Tạo 1 Google Sheet mới (trên Drive của bạn, ví dụ đặt tên "PhotoSwap Billing Log").
 * 2. Trong Sheet đó: Extensions > Apps Script.
 * 3. Xoá hết code mẫu (myFunction...), dán TOÀN BỘ nội dung file này vào.
 * 4. Bấm biểu tượng Save (💾).
 * 5. Bấm nút "Deploy" (góc trên phải) > "New deployment".
 *    - Bấm biểu tượng bánh răng cạnh "Select type" > chọn "Web app".
 *    - Description: tuỳ ý, ví dụ "PhotoSwap billing webhook".
 *    - Execute as: "Me" (tài khoản Google của bạn).
 *    - Who has access: "Anyone" (bắt buộc, để máy bạn bè gửi được dữ liệu lên).
 *    - Bấm "Deploy".
 *    - Google có thể yêu cầu bạn "Authorize access" — chọn tài khoản của bạn,
 *      bấm "Advanced" > "Go to (tên project) (unsafe)" > "Allow".
 *      (Đây là bình thường vì đây là script do chính bạn viết/dán, không phải app lạ.)
 * 6. Sau khi Deploy xong, copy dòng "Web app URL" — đó chính là giá trị bạn cần
 *    dán vào biến REMOTE_LOG_WEBHOOK_URL ở đầu file app_web.py (hoặc vào
 *    .streamlit/secrets.toml với key remote_log_webhook_url).
 * 7. (Tuỳ chọn) Vào Sheet > nút "Share" > "Anyone with the link" > "Viewer",
 *    copy link đó dán vào REMOTE_SHEET_VIEW_URL để có nút mở nhanh trong app.
 *
 * LƯU Ý: Nếu sau này bạn sửa lại script này, phải bấm "Deploy" > "Manage deployments"
 * > biểu tượng bút chì > đổi "Version" thành "New version" > Deploy lại,
 * thì các thay đổi mới có hiệu lực (không tự áp dụng khi chỉ Save).
 */

function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

  // Nếu sheet đang trống, tự thêm dòng tiêu đề
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      "timestamp", "user", "model", "resolution",
      "format", "ref_image", "status", "cost_usd", "cost_vnd",
    ]);
  }

  try {
    var data = JSON.parse(e.postData.contents);
    sheet.appendRow([
      data.timestamp || "",
      data.user || "",
      data.model || "",
      data.resolution || "",
      data.format || "",
      data.ref_image || "",
      data.status || "",
      data.cost_usd || 0,
      data.cost_vnd || 0,
    ]);
    return ContentService
      .createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
