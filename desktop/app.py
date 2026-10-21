"""Native offline shell with asynchronous, bounded snapshot reads."""
import os,sys,argparse,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QObject, Signal, Slot, Property, QUrl, QTimer
from PySide6.QtGui import QGuiApplication, QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from .repository import Repository, ROOT

class Bridge(QObject):
    changed=Signal()
    finished=Signal(str,int,object)
    def __init__(self):
        super().__init__();self.repo=Repository();self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='snapshot')
        self._state={'ready':False,'error':'','page':'Overview','marketRows':[],'detail':{},'overview':{},'search':'','offset':0,'more':False}
        self.serial={};self.finished.connect(self.receive)
    @Property('QVariantMap',notify=changed)
    def state(self):return self._state
    def request(self,kind,fn,*args):
        n=self.serial.get(kind,0)+1;self.serial[kind]=n
        f=self.pool.submit(fn,*args)
        def done(f):
            try: result=f.result()
            except Exception as e: result={'error':str(e)}
            self.finished.emit(kind,n,result)
        f.add_done_callback(done)
    @Slot(str,int,object)
    def receive(self,kind,n,value):
        if n!=self.serial.get(kind):return
        if 'error' in value:self._state['error']=value['error']
        elif kind=='overview':self._state.update(overview=value,ready=True)
        elif kind=='markets':self._state.update(marketRows=value['rows'],more=value['more'],offset=value['offset'])
        elif kind=='detail':self._state['detail']=value
        self.changed.emit()
    @Slot()
    def load(self):
        self.request('overview',self.repo.overview);self.request('markets',self.repo.markets)
        self.request('detail',self.repo.detail,'CONTROLS-2026-D')
    @Slot(str)
    def navigate(self,page):
        self._state['page']=page
        if page=='Research':
            cohort=self._state['overview'].get('cohorts',{}).get('research',{}).get('rows',[])
            if cohort and self._state['detail'].get('ticker') not in [r['ticker'] for r in cohort]:
                self.select(cohort[0]['ticker'])
        self.changed.emit()
    @Slot(str)
    def search(self,text):
        self._state['search']=text;self.request('markets',self.repo.markets,text,0)
    @Slot(int)
    def pageMarkets(self,delta):
        self.request('markets',self.repo.markets,self._state['search'],max(0,self._state['offset']+50*delta))
    @Slot(str)
    def select(self,ticker):self.request('detail',self.repo.detail,ticker)
    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture-dir',type=Path)
    p.add_argument('--smoke',action='store_true')
    p.add_argument('--interaction-test',action='store_true')
    p.add_argument('--compact',action='store_true')
    args=p.parse_args(argv)
    app=QGuiApplication(sys.argv[:1]);app.setApplicationName('Kalshi Hunter');app.setOrganizationName('Local Research')
    app.setFont(QFont('Inter',10))
    bridge=Bridge();engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',bridge)
    errors=[]
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Main.qml')))
    if not engine.rootObjects():
        print(errors, file=sys.stderr);bridge.close();return 1
    app.aboutToQuit.connect(bridge.close);QTimer.singleShot(0,bridge.load)
    if args.compact:
        engine.rootObjects()[0].resize(1100,760)
    if args.interaction_test:
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt, QPointF
        def interact():
            window=engine.rootObjects()[0]
            def click_item(name):
                def find(item):
                    if item.objectName()==name:return item
                    for child in item.childItems():
                        result=find(child)
                        if result is not None:return result
                    return None
                item=find(window.contentItem())
                if item is None: raise AssertionError('Missing '+name)
                pos=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()
                QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,pos)
                QTest.qWait(250)
            try:
                click_item('nav_Markets')
                assert bridge.state['page']=='Markets'
                click_item('market_search')
                for ch in 'CONTROL': QTest.keyClick(window,ord(ch))
                import time
                for _ in range(150):
                    time.sleep(.02);app.processEvents()
                    if bridge.state['marketRows'] and all('CONTROL' in r['ticker'].upper() or 'CONTROL' in r['title'].upper() for r in bridge.state['marketRows']):break
                assert bridge.state['search'].upper()=='CONTROL'
                assert bridge.state['marketRows'] and all('CONTROL' in r['ticker'].upper() or 'CONTROL' in r['title'].upper() for r in bridge.state['marketRows'])
                for page in ['Research','Strategy','Accuracy','Positions','Evidence','Overview']:
                    click_item('nav_'+page)
                    assert bridge.state['page']==page
                assert not errors, errors
                print(json.dumps({'interaction_test':'passed','qml_warnings':errors}))
                app.exit(0)
            except Exception as e:
                import traceback;traceback.print_exc();app.exit(1)
        QTimer.singleShot(1800,interact)
    if args.capture_dir or args.smoke:
        pages=iter(['Overview','Markets','Research','Strategy','Alerts','Positions','History','Accuracy','Evidence'])
        current=[None];ticks=[0]
        timer=QTimer();timer.setInterval(800)
        def capture():
            ticks[0]+=1
            if ticks[0]>60:
                print('Snapshot load timeout',file=sys.stderr);app.exit(2);return
            if not bridge.state['ready'] or not bridge.state['detail']:return
            if current[0] and args.capture_dir:
                args.capture_dir.mkdir(parents=True,exist_ok=True)
                engine.rootObjects()[0].grabWindow().save(str(args.capture_dir/(current[0].lower()+'.png')))
            try:
                current[0]=next(pages);bridge.navigate(current[0])
            except StopIteration:
                print(json.dumps({'ready':True,'pages':9,'qml_warnings':errors}))
                app.exit(1 if errors else 0)
        timer.timeout.connect(capture);timer.start()
    return app.exec()

if __name__=='__main__':sys.exit(main())
