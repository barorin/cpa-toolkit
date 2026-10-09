// 有報サーチ(jicpa.esper-search.com) 操作ヘルパー
// 使い方: このファイル全体 + 末尾に呼び出し1行を javascript_tool にそのまま渡す。
//   例) <このファイル>\nawait YUHO.search({keywords:'のれん 減損', tocLabels:['重要な会計上の見積り（連結）']})
// 前提: タブが https://jicpa.esper-search.com/ufosearch/default.aspx(フレーム構成)を表示していること。
// 一度読み込めば window.YUHO として同じタブに残る(ページを再読込したら再読込が必要)。
// 注意: javascript_tool は実行結果に URL・クエリ文字列・長い英数字列があると [BLOCKED] に置き換え、
//       長い単一文字列は約1000字で切り詰める。返り値は URL を含まないテキスト、長文は配列で返すこと。
window.YUHO = (() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  // URL のクエリ記号は文字コードで組み立てる(javascript_tool がクエリ文字列らしき文字列をマスクする挙動への予防。
  // 入力側でマスクされるかは未確認だが、この書き方で動作確認済みなので変えないこと)
  const Q = String.fromCharCode(63), EQ = String.fromCharCode(61), AMP = String.fromCharCode(38);
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const noUrl = (s) => (s || '').replace(/https?:\/\/[^\s　）)」』>]+/g, '[URL]').replace(/www\.[^\s　）)」』>]+/g, '[URL]');
  const pad = (n) => String(n).padStart(2, '0');
  const fmtLocal = (dt) => dt.getFullYear() + '-' + pad(dt.getMonth() + 1) + '-' + pad(dt.getDate());

  function frames() {
    try {
      const main = window.top.frames['main'];
      if (!main || !main.frames['doc'] || !main.frames['tab']) throw 0;
      return { tab: main.frames['tab'], doc: main.frames['doc'] };
    } catch (e) {
      throw new Error('有報サーチの画面(default.aspx)ではない。セッション切れの可能性。ログインからやり直す');
    }
  }
  const mainDoc = () => frames().doc;

  // cond() が真になるまで待つ(タイムアウトで false)
  async function waitFor(cond, timeoutMs = 15000, interval = 500) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      try { if (cond()) return true; } catch (e) {}
      await sleep(interval);
    }
    return false;
  }
  // doc フレームが別の document に差し替わり、読込完了するまで待つ
  const waitDocReplaced = (oldDoc, extra = () => true, timeoutMs = 20000) =>
    waitFor(() => { const d = mainDoc().document; return d !== oldDoc && d.readyState === 'complete' && extra(d); }, timeoutMs);
  // 同一 document 内の非同期ポストバック(UpdatePanel)が終わるまで待つ
  async function waitIdle(d, minMs = 1500) {
    await sleep(minMs);
    return waitFor(() => { const p = d.getElementById('UpdateProgress1'); return !p || p.style.display === 'none'; }, 15000);
  }

  // 上部タブの切替。外部には公開しない(設定タブやログアウトを触らないため、許可した id のみ)
  const TABS = ['search', 'result', 'document'];
  async function tab(id) {
    if (!TABS.includes(id)) throw new Error('許可されていないタブ: ' + id);
    const el = frames().tab.document.getElementById(id);
    if (!el || !el.classList.contains('tabImg')) return false;
    const old = mainDoc().document;
    el.click();
    await waitDocReplaced(old, () => true, 10000);
    return true;
  }

  async function ensureSearchForm() {
    const ok = () => { try { return !!mainDoc().document.getElementById('tbKeywordAndOr'); } catch (e) { return false; } };
    if (!ok()) await tab('search');
    if (!(await waitFor(ok, 8000))) throw new Error('検索フォームが見つからない。画面上部の「検索」タブを手動クリックしてから再実行');
    return mainDoc().document;
  }

  // 目次選択画面(本来はポップアップ)を非表示 iframe で開く。タイムアウト時は iframe を消して null
  async function openTocFrame(binder) {
    const d = await ensureSearchForm();
    d.querySelectorAll('iframe.cc_toc').forEach((x) => x.remove());
    const f = d.createElement('iframe'); f.className = 'cc_toc'; f.style.display = 'none'; d.body.appendChild(f);
    f.src = '/ufosearch/searchForms/selectToc.aspx' + Q + 'binder' + EQ + binder + AMP + 'binder_toc' + EQ;
    const ok = await waitFor(() => f.contentDocument && f.contentDocument.readyState === 'complete' && f.contentDocument.getElementById('btnSendVal'), 15000);
    if (!ok) { f.remove(); return null; }
    f.contentWindow.alert = (m) => { f.dataset.alert = m; };
    return f;
  }
  const GREEN = 'rgb(0, 162, 65)';
  function tocItems(td) {
    return [...td.querySelectorAll('input[type=checkbox][id^=cblToc]')].map((c) => {
      const l = td.querySelector('label[for="' + c.id + '"]');
      return { c, label: clean(l ? l.innerText : '').replace(/\s*≫$/, ''), green: !!l && getComputedStyle(l).color === GREEN };
    });
  }

  // 目次ラベル -> {value,text}。labels は完全一致(末尾の「 ≫」「 [緑]」は無視)。前方一致は末尾に *。
  // 同時指定はサイトの制限で 10 項目まで、うち緑(XBRL詳細タグ)は 3 項目まで。超える場合はエラーを返す。
  async function resolveToc(binder, labels) {
    const f = await openTocFrame(binder);
    if (!f) return { error: '目次選択画面を読み込めない(時間切れ)。再実行する' };
    const td = f.contentDocument, items = tocItems(td);
    const missing = [], picked = new Set();
    for (const raw of labels) {
      const want = clean(raw).replace(/\s*\[緑\]$/, '').replace(/\s*≫$/, '');
      const pre = want.endsWith('*'), w = want.replace(/\*$/, '');
      const hit = items.filter((x) => (pre ? x.label.startsWith(w) : x.label === w));
      if (!hit.length) missing.push(raw); hit.forEach((x) => picked.add(x));
    }
    if (missing.length) { f.remove(); return { error: '目次ラベルが見つからない', missing, hint: 'YUHO.listToc(binder, 語) で正確なラベルを確認' }; }
    const n = picked.size, g = [...picked].filter((x) => x.green).length;
    if (n > 10 || g > 3) {
      f.remove();
      return { error: '目次の同時指定上限超過(全体10・緑3まで)', selected: n, green: g, labels: [...picked].map((x) => x.label + (x.green ? ' [緑]' : '')) };
    }
    picked.forEach((x) => (x.c.checked = true));
    td.getElementById('btnSendVal').click();
    await waitFor(() => f.dataset.alert || (f.contentDocument !== td && f.contentDocument.readyState === 'complete' &&
      f.contentDocument.getElementById('hdnValue') && !['', 'sendVal'].includes(f.contentDocument.getElementById('hdnValue').value)), 15000);
    const nd = f.contentDocument, alertMsg = f.dataset.alert;
    const value = nd && nd.getElementById('hdnValue') ? nd.getElementById('hdnValue').value : '';
    const text = nd && nd.getElementById('hdnText') ? nd.getElementById('hdnText').value : '';
    f.remove();
    if (alertMsg) return { error: '目次選択でサイトが警告: ' + alertMsg };
    if (!value || value === 'sendVal' || !text) return { error: '目次コードを取得できない(時間切れ)。再実行する' };
    return { value, text };
  }

  // 目次ラベル一覧(filter で部分一致絞込み)。[緑] は XBRL 詳細タグの項目
  async function listToc(binder = 'ufo', filter = '') {
    const f = await openTocFrame(binder);
    if (!f) return { error: '目次選択画面を読み込めない(時間切れ)。再実行する' };
    const out = tocItems(f.contentDocument).map((x) => x.label + (x.green ? ' [緑]' : '')).filter((s) => s && s.includes(filter));
    f.remove(); return out;
  }

  // 並び順の選択肢は直前の検索の日付種別で変わる(決算日モード: relevant_date,* / 提出日モード: filing_date,*)。
  // date_* は画面にある方の日付で並べる
  const SORT = { score: /^score,desc$/, date_desc: /^(relevant|filing)_date,desc$/, date_asc: /^(relevant|filing)_date,asc$/, code_asc: /^edinet_code,asc$/, code_desc: /^edinet_code,desc$/ };
  const BINDERS = ['ufo', 'hanpo', 'shihanki', 'rinpo', 'teisei', 'tousei', 'tdnet_tanshin_pdf', 'tdnet_others_pdf', 'ufo_attach_pdf'];

  // 検索実行。opts:
  //  keywords(必須,空白区切り) / mode:'and'|'or' / exclude(除外語)
  //  binder:'ufo'(有報,既定)|'hanpo'(半期)|'shihanki'(四半期)|'rinpo'(臨時)|'teisei'(訂正)|'tousei'(内部統制)
  //         |'tdnet_tanshin_pdf'(短信)|'tdnet_others_pdf'(その他適時開示)|'ufo_attach_pdf'(招集通知等)
  //  tocLabels:[目次ラベル] / dateType:'filed'(提出日,既定)|'fiscal'(決算日) / from,to:'YYYY-MM-DD'(既定: 直近1年)
  //  industry(東証業種コード 例'3650') / exchange(例'東証プライム') / fiscalMonth('03') / consolidated:'連結'|'非連結'
  //  accounting:'日本基準'|'IFRS'|'SEC'|'日本基準以外' / auditor(監査法人名) / goingConcern:'あり'|'なし'
  //  perPage:10|20|40 / sort:'date_desc'(既定)|'date_asc'|'score'|'code_asc'|'code_desc' / kwic:0|25|40
  //  (date_* の日付は、直前の検索の日付種別に応じて決算日または提出日になる)
  async function search(o) {
    if (!o || !clean(o.keywords)) throw new Error('keywords は必須');
    const binder = o.binder || 'ufo';
    if (!BINDERS.includes(binder)) throw new Error('binder が不正: ' + binder);
    const sort = SORT[o.sort || 'date_desc'];
    if (!sort) throw new Error('sort が不正: ' + o.sort + '(' + Object.keys(SORT).join('|') + ')');
    let d = await ensureSearchForm();
    const bl = d.getElementById('ddlBinderList');
    if (bl.value !== binder) {
      // 書類種別だけは change を発火させる(目次ボタン等がサーバー側で切り替わるため)。終わるまで待ってから他を設定
      bl.value = binder; bl.dispatchEvent(new Event('change', { bubbles: true }));
      await waitIdle(d);
      d = await ensureSearchForm();
      if (d.getElementById('ddlBinderList').value !== binder) throw new Error('書類種別を切り替えられない: ' + binder);
    }
    let toc = { value: '', text: '－指定なし－' };
    if (o.tocLabels && o.tocLabels.length) { toc = await resolveToc(binder, o.tocLabels); if (toc.error) return toc; d = await ensureSearchForm(); }

    // 重要: 以降は change イベントを発火させない(年・月の change で月や目次が無言でリセットされる)
    const sv = (id, v) => {
      const e = d.getElementById(id); if (!e) throw new Error('要素なし: ' + id);
      if (e.disabled) throw new Error(id + ' が無効状態(画面の状態を確認)');
      e.value = v; if (e.value !== String(v)) throw new Error(id + ' に ' + v + ' を設定できない');
    };
    const ymd = (s, name) => {
      const m = String(s).match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
      if (!m) throw new Error(name + ' は YYYY-MM-DD 形式で指定: ' + s);
      return [m[1], pad(m[2]), pad(m[3])];
    };
    d.getElementById(o.mode === 'or' ? 'rdoFulltextCondOr' : 'rdoFulltextCondAnd').checked = true;
    sv('tbKeywordAndOr', clean(o.keywords)); sv('tbKeywordNot', clean(o.exclude));
    sv('targetTocValue', toc.value); sv('tbBinderToc', toc.text);
    const today = new Date(), ago = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
    const [fy, fm, fd] = ymd(o.from || fmtLocal(ago), 'from'), [ty, tm, tdd] = ymd(o.to || fmtLocal(today), 'to');
    const filed = (o.dateType || 'filed') === 'filed', s2 = filed ? '2' : '';
    d.getElementById(filed ? 'rdoDate2' : 'rdoDate1').checked = true;
    sv('ddlYearFrom' + s2, fy); sv('ddlMonthFrom' + s2, fm); sv('ddlDayFrom' + s2, fd);
    sv('ddlYearTo' + s2, ty); sv('ddlMonthTo' + s2, tm); sv('ddlDayTo' + s2, tdd);
    sv('ddlIndustry', o.industry || 'false');
    sv('ddlExchange', o.exchange || 'false');
    sv('ddlFiscaldate', o.fiscalMonth || 'false');
    sv('ddlConsoli', { '連結': '0', '非連結': '10' }[o.consolidated] || 'false');
    sv('ddlAccounting', { '日本基準': '0', '日本基準以外': '1,2', 'SEC': '1', 'IFRS': '2' }[o.accounting] || 'false');
    sv('ddlDoubtFlg', { 'あり': '1', 'なし': '0' }[o.goingConcern] || 'false');
    sv('tbAuditFirm', clean(o.auditor));
    const wl = d.getElementById('cbWatchListGroup'); if (wl) wl.checked = false;
    sv('ddlResultViewNum', String(o.perPage || 20));
    const sortOpt = [...d.getElementById('ddlResultViewSort').options].find((x) => sort.test(x.value));
    if (!sortOpt) throw new Error('並び順の選択肢が見つからない: ' + (o.sort || 'date_desc'));
    sv('ddlResultViewSort', sortOpt.value);
    sv('ddlResultViewKWIC', String(o.kwic ?? 40));
    const formDoc = d;
    formDoc.getElementById('btnSubmit').click();
    const ok = await waitDocReplaced(formDoc, (nd) => !nd.getElementById('tbKeywordAndOr') && nd.body.innerText.length > 50, 30000);
    if (!ok) return { error: '検索結果が表示されない(時間切れ)。スクリーンショットで状態確認' };
    return results();
  }

  // 現在の検索結果ページを構造化して返す
  function results() {
    const rd = mainDoc().document;
    const t = rd.getElementById('tblHitlistFulltext');
    const body = clean(rd.body.innerText);
    const condition = clean((body.match(/〔.*〕/) || [''])[0]);
    if (!t) {
      if (body.includes('見つかりません')) return { condition, summary: '0件', hits: [] };
      return { error: '検索結果画面ではない', page: noUrl(body).slice(0, 300), hits: [] };
    }
    if (!condition) return { error: '検索条件欄を読めない(画面構成の変更の可能性)', hits: [] };
    const rows = [...t.rows], hits = [];
    rows.forEach((r, i) => {
      if (r.className !== 'odd' && r.className !== 'even') return;
      const c = [...r.cells].map((x) => clean(x.innerText));
      const m = c[1].match(/(\d+)\s*\[(\d+)\]/) || [];
      const comp = c[2].match(/^(\S+)\s*［(E\d+)］\s*(.*)$/) || [];
      hits.push({ no: +m[1], hitCount: +m[2], secCode: comp[1], edinet: comp[2], company: comp[3] || c[2],
        industry: c[3], docDate: c[4], section: c[5], auditor: c[6],
        kwic: [...new Set(noUrl(clean(rows[i + 1] && rows[i + 1].className === '' ? rows[i + 1].innerText : ''))
          .replace(/－－－他、.*$/, '').split(/・・・\s*・・・|・・・/).map(clean).filter(Boolean))].slice(0, 6) });
    });
    return { condition, summary: clean(rows[0].innerText).split('［')[0], hits };
  }

  // 次ページ。表示可能件数は300件まで
  async function next() {
    const rd = mainDoc().document;
    if (!rd.getElementById('tblHitlistFulltext')) return { error: '検索結果画面ではない。YUHO.backToResults() を先に実行' };
    const a = [...rd.querySelectorAll('a')].find((x) => x.innerText.includes('次の'));
    if (!a) return { error: '次ページなし' };
    const before = results().summary;
    a.click();
    const ok = await waitDocReplaced(rd, (nd) => !!nd.getElementById('tblHitlistFulltext'));
    const r = results();
    if (!ok || r.summary === before) return { error: '次ページに切り替わらない(時間切れ)', summary: r.summary };
    return r;
  }

  // 検索結果の no 番目(結果番号)の該当箇所を開き、本文を返す(chunks 配列。続きは text())
  let lastBody = '';
  async function open(no, maxChars = 8000) {
    const rd = mainDoc().document;
    const t = rd.getElementById('tblHitlistFulltext');
    if (!t) return { error: '検索結果画面ではない。YUHO.backToResults() を先に実行' };
    const row = [...t.rows].find((r) => (r.className === 'odd' || r.className === 'even') && parseInt(clean(r.cells[1].innerText)) === no);
    if (!row) return { error: 'このページに結果番号 ' + no + ' がない(next() でページを進める)' };
    const a = row.cells[5] && row.cells[5].querySelector('a');
    if (!a) return { error: '結果番号 ' + no + ' に文書リンクがない' };
    const meta = { company: clean(row.cells[2].innerText), section: clean(row.cells[5].innerText) };
    a.click();
    let body = '', tools = '';
    const ok = await waitDocReplaced(rd, () => {
      tools = clean(mainDoc().frames['doc-tools'].document.body.innerText);
      const bd = mainDoc().frames['doc-body'].document;
      body = bd.body.innerText;
      return bd.readyState === 'complete' && !!tools && body.length > 5;
    });
    if (!ok || !body) return { error: '本文を取得できない(時間切れ)。スクリーンショットで状態確認', ...meta };
    lastBody = noUrl(body).replace(/[ \t　 ]+/g, ' ').replace(/ ?\n[ \n]*/g, '\n').trim();
    return { ...meta, header: noUrl(tools).replace(/^.*?印刷用出力\s*/, ''), length: lastBody.length, ...text(0, maxChars) };
  }

  // 直近に open() した本文を offset から len 文字返す(700字ごとの配列)
  function text(offset = 0, len = 20000) {
    if (!lastBody) return { error: '本文がない。先に YUHO.open(no) を実行' };
    offset = Math.max(0, offset | 0);
    const s = lastBody.slice(offset, offset + len), chunks = [];
    for (let i = 0; i < s.length; i += 700) chunks.push(s.slice(i, i + 700));
    const end = offset + s.length;
    return { offset, nextOffset: end < lastBody.length ? end : null, chunks };
  }

  async function backToResults() {
    await tab('result');
    if (!(await waitFor(() => !!mainDoc().document.getElementById('tblHitlistFulltext') || mainDoc().document.body.innerText.includes('見つかりません'), 10000)))
      return { error: '検索結果一覧に戻れない', hits: [] };
    return results();
  }

  return { search, results, next, open, text, backToResults, resolveToc, listToc };
})();
