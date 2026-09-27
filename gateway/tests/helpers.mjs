import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
export class D1 {
  constructor(){this.db=new DatabaseSync(':memory:');for(const name of ['0001_pilot.sql','0002_login_coupons.sql','0003_coupon_money.sql'])this.db.exec(readFileSync(new URL('../migrations/'+name,import.meta.url),'utf8'));}
  prepare(query){return this.statement(query,[]);}
  statement(query,args){const db=this.db;return {
    bind:(...next)=>this.statement(query,next),
    first:async()=>db.prepare(query).get(...args)||null,
    all:async()=>({results:db.prepare(query).all(...args),success:true}),
    run:async()=>({meta:db.prepare(query).run(...args),success:true}),
    execute:()=>{const stmt=db.prepare(query);return stmt.columns().length?{results:stmt.all(...args),success:true}:{results:[],meta:stmt.run(...args),success:true};}
  };}
  async batch(statements){this.db.exec('BEGIN IMMEDIATE');try{const results=statements.map(s=>s.execute());this.db.exec('COMMIT');return results;}catch(e){this.db.exec('ROLLBACK');throw e;}}
}
