const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..');
const qrgen=require(path.join(root,'sparkle_coder/ui/qrcode.js'));
const qr=qrgen(0,'M');
qr.addData('upi://pay?pa=owner%40bank&pn=Owner&am=15.00&cu=INR&tn=SPARKLE+CODER+tokens');
qr.make();
const svg=qr.createSvgTag({cellSize:4,margin:0,scalable:true});
assert.match(svg,/^<svg/);
assert.match(svg,/viewBox=/);

const app=fs.readFileSync(path.join(root,'sparkle_coder/ui/app.js'),'utf8');
const scratchHtml=fs.readFileSync(path.join(root,'gateway/public/scratch.html'),'utf8');
const scratchJs=fs.readFileSync(path.join(root,'gateway/public/app.js'),'utf8');
const index=fs.readFileSync(path.join(root,'sparkle_coder/ui/index.html'),'utf8');

for(const source of [app,scratchHtml,scratchJs]) {
  assert.ok(source.includes('upiPaymentBlock'),'UPI payment block missing');
}
assert.ok(index.includes('/qrcode.js'));
assert.ok(scratchHtml.includes('/qrcode.js'));
assert.ok(app.includes("id('upiPaymentBlock').hidden=free||!configured"));
assert.ok(app.includes("id('paymentReferenceRow').hidden=free||!configured"));
assert.ok(app.includes("quotePending"));
assert.ok(app.includes("resolveAccountCoupon"));
assert.ok(app.includes("Check coupon and continue"));
assert.ok(app.includes("Submit ₹0 coupon for review"));
assert.ok(app.includes("No UPI payment or transaction reference is needed"));
assert.ok(app.includes("<strong id=\"payUpiId\">—</strong>"));
assert.ok(scratchJs.includes('$("upiPaymentBlock").hidden=free||!configured'));
assert.ok(scratchJs.includes('$("paymentReferenceRow").hidden=free||!configured'));
assert.ok(scratchJs.includes('resolveCouponQuote'));
assert.ok(scratchJs.includes('Check coupon and continue'));
assert.ok(scratchJs.includes('Submit ₹0 coupon for review'));
assert.ok(scratchHtml.indexOf('id="upiQr"') < scratchHtml.indexOf('id="upiId"'));

console.log('Payment UI: paid purchases show self-hosted UPI QR + ID; ₹0 coupons require no UPI/UTR.');
