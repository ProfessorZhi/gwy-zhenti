"""Numbered exam integrity: internally consecutive IDs cannot prove completeness."""
def reference_number_issues(qids, meta):
    expected = meta.get('对照题本题量')
    missing = meta.get('缺失原题号')
    if expected is None:
        return ['题号非连续（需核原卷）'] if qids and qids != list(range(1,len(qids)+1)) else []
    if not isinstance(expected,int) or isinstance(expected,bool) or expected<=0:
        return ['对照题量字段无效']
    if not isinstance(missing,list) or any(not isinstance(n,int) or isinstance(n,bool) for n in missing):
        return ['缺失原题号字段无效']
    if len(set(missing))!=len(missing) or any(n<1 or n>expected for n in missing):
        return ['缺失原题号字段无效']
    issues=[]
    actual=set(qids); full=set(range(1,expected+1)); declared=set(missing)
    if actual & declared or actual | declared != full:
        issues.append('原题号与已声明缺口不一致')
    if qids != sorted(actual):issues.append('原题号重复或乱序')
    if missing:issues.append('已确认仍缺原题号：'+ '、'.join(map(str,sorted(missing))))
    if meta.get('实有题数') is not None and meta['实有题数']!=len(qids):issues.append('实有题数与正文不符')
    return issues
