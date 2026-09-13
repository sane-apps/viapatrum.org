const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),os=require("node:os"),path=require("node:path"),crypto=require("node:crypto");
const {spawnSync}=require("node:child_process");
const {artifact,verifyReview,REQUIRED_SHOTS,REQUIRED_CHECKS}=require("./check_catalogue_ui.cjs");
const hash=x=>crypto.createHash("sha256").update(x).digest("hex");
test("visual gate rejects stale build, changed image, missing review, and missing coverage",()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),"fathers-visual-gate-test-")),out=path.join(root,"outputs/ui-review");
 try {
  fs.mkdirSync(path.join(root,"dist/assets"),{recursive:true});fs.mkdirSync(path.join(root,"scripts"));fs.mkdirSync(out,{recursive:true});
  for(const [name,body] of [["dist/assets/site.css","body{}"],["dist/assets/site.js","test"],["dist/index.html","known text"],["scripts/check_catalogue_ui.cjs","test runner"]])fs.writeFileSync(path.join(root,name),body);
  const r={schema:2,status:"passed",artifact:artifact(root),started:"2026-09-13T00:00:00Z",completed_checks:REQUIRED_CHECKS,errors:[],review:{status:"passed",method:"image-inspection",reviewer:"fixture-only",reviewed_at:"2026-09-13T00:01:00Z"},screenshots:REQUIRED_SHOTS.map(name=>{
   const bytes=Buffer.from("fixture image "+name);fs.writeFileSync(path.join(out,name),bytes);
   return {path:name,sha256:hash(bytes),inspected:true,result:"Test fixture only: not a real release review.",geometry:{failures:[]}};
  })};
  const save=()=>fs.writeFileSync(path.join(out,"browser-receipt.json"),JSON.stringify(r));
  save();assert.equal(verifyReview(root).status,"passed");
  fs.writeFileSync(path.join(root,"dist/index.html"),"changed translation");assert.throws(()=>verifyReview(root),/changed after review/);
  fs.writeFileSync(path.join(root,"dist/index.html"),"known text");
  const first=r.screenshots[0];fs.writeFileSync(path.join(out,first.path),"tampered");assert.throws(()=>verifyReview(root),/Screenshot changed/);
  fs.writeFileSync(path.join(out,first.path),"fixture image "+first.path);
  first.inspected=false;save();assert.throws(()=>verifyReview(root),/not inspected/);first.inspected=true;
  r.review.status="pending";save();assert.throws(()=>verifyReview(root),/actual agent visual review/);r.review.status="passed";
  const shot=r.screenshots.pop();save();assert.throws(()=>verifyReview(root),/Missing\/duplicate visual states/);r.screenshots.push(shot);
  r.completed_checks=[];save();assert.throws(()=>verifyReview(root),/Incomplete browser checks/);r.completed_checks=REQUIRED_CHECKS;
  first.geometry.failures=["overflow"];save();assert.throws(()=>verifyReview(root),/Layout errors/);first.geometry.failures=[];
  save();fs.writeFileSync(path.join(root,"scripts/check_catalogue_ui.cjs"),"weaker runner");assert.throws(()=>verifyReview(root),/changed after review/);
 } finally {spawnSync("trash",[root],{stdio:"ignore"});}
});
test("ship kernel lock blocks a competing skip-build before build or upload",()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),"fathers-ship-lock-test-"));
 try {
  fs.mkdirSync(path.join(root,"scripts"));fs.mkdirSync(path.join(root,"outputs"));
  fs.copyFileSync(path.join(__dirname,"ship.sh"),path.join(root,"scripts/ship.sh"));
  const command='exec 9>"$1/outputs/ship.lock"; python3 -c "import fcntl;fcntl.flock(9,fcntl.LOCK_EX|fcntl.LOCK_NB)"; FATHERS_BUILD_PYTHON=/missing bash "$1/scripts/ship.sh" --skip-build --dry-run; status=$?; exit "$status"';
  const r=spawnSync("bash",["-c",command,"lock-test",root],{encoding:"utf8",timeout:10000});
  assert.equal(r.status,1);assert.match(r.stderr,/another Fathers ship holds/);
 } finally {spawnSync("trash",[root],{stdio:"ignore"});}
});
