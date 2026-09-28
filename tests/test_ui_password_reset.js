const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..');
const app=fs.readFileSync(path.join(root,'sparkle_coder/ui/app.js'),'utf8');
const scratch=fs.readFileSync(path.join(root,'gateway/public/scratch.html'),'utf8');
const scratchJs=fs.readFileSync(path.join(root,'gateway/public/app.js'),'utf8');
const adapter=fs.readFileSync(path.join(root,'gateway/public/cloud-adapter.js'),'utf8');
const admin=fs.readFileSync(path.join(root,'gateway/public/admin.js'),'utf8');

for(const source of [app,scratch]) {
  assert.ok(source.includes('Forgot password?'));
  assert.ok(source.includes('Reset password and sign in'));
  assert.ok(source.includes('passwordResetEmail'));
  assert.ok(source.includes('passwordResetCode'));
  assert.ok(source.includes('passwordResetPassword'));
}
assert.ok(app.includes("/account/password/reset"));
assert.ok(scratchJs.includes('/api/password/reset'));
assert.ok(adapter.includes("/account/password/reset"));
assert.ok(adapter.includes("/api/password/reset"));
assert.ok(admin.includes('Create reset code'));
assert.ok(admin.includes('password-reset'));
console.log('Password reset UI: user reset form and admin one-time reset-code controls are wired.');
