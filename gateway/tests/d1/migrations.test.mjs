// Use the actual Wrangler + local D1 runtime, separate from the fast SQLite suite.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdirSync,mkdtempSync,readFileSync,readdirSync,rmSync,writeFileSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

test('Wrangler applies the schema once and file import records the same schema and history', {timeout:120000},()=>{
 const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
 mkdirSync(join(root,'.wrangler'),{recursive:true});
 const temporary=mkdtempSync(join(root,'.wrangler','migration-check-'));
 try {
  const config={name:'sparkle-migration-check',compatibility_date:'2026-09-01',
   d1_databases:[{binding:'DB',database_name:'migration-check',database_id:'11111111-2222-3333-4444-555555555555',migrations_dir:join(root,'migrations')}]};
  const configPath=join(temporary,'wrangler.json');writeFileSync(configPath,JSON.stringify(config));
  const run=(state,...args)=>execFileSync(process.execPath,[join(root,'node_modules/wrangler/bin/wrangler.js'),
   'd1',...args,'--local','--persist-to',join(temporary,state),'--config',configPath],
   {cwd:root,encoding:'utf8',timeout:30000,env:{...process.env,CI:'1',WRANGLER_SEND_METRICS:'false',WRANGLER_LOG_PATH:join(temporary,'wrangler.log')}});
  const query=(state,sql)=>JSON.parse(run(state,'execute','migration-check','--command',sql,'--json')).flatMap(r=>r.results);
  const names = readdirSync(join(root,'migrations'))
    .filter(name => /^\d{4}_[a-z0-9_]+\.sql$/.test(name)).sort();
  assert.ok(names.length >= 7, 'Expected the initial schema and flexible-purchase migration');
  const migrations = names.map(name => ({name}));
  const queryMigrations = state => query(state,'SELECT name FROM d1_migrations ORDER BY name');
  run('normal','migrations','apply','migration-check');
  assert.deepEqual(queryMigrations('normal'), migrations);
  assert.ok(query('normal',"SELECT COUNT(*) AS n FROM sqlite_master WHERE type='trigger'")[0].n >= 14);
  query('normal',"INSERT INTO accounts(id,email,name,created) VALUES ('keep','keep@example.test','Keep this account',1)");
  run('normal','migrations','apply','migration-check');
  assert.deepEqual(query('normal','SELECT name FROM accounts'),[{name:'Keep this account'}]);

  query('import','CREATE TABLE d1_migrations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)');
  const file=join(temporary,'recovery.sql');
  // A recovery import must reproduce every currently tracked migration,
  // not just the six migrations that existed when this test was first written.
  const schema = names.map(name => readFileSync(join(root,'migrations',name),'utf8')).join('\n');
  const escaped = names.map(name => "('"+name.replaceAll("'","''")+"')").join(',');
  writeFileSync(file,schema+"\nINSERT INTO d1_migrations(name) VALUES "+escaped+";\n");
  run('import','execute','migration-check','--file',file,'--yes');
  assert.deepEqual(queryMigrations('import'), migrations);
  const objects="SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name";
  assert.deepEqual(query('normal',objects),query('import',objects));
 } finally {rmSync(temporary,{recursive:true,force:true});}
});
