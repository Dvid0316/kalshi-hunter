import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1440; height: 1000; minimumWidth: 1100; minimumHeight: 760
    visible: true; title: "Kalshi Hunter · Offline research"
    color: "#0b111a"
    property color ink: "#e7eef7"
    property color muted: "#92a5bc"
    property color accent: "#55dcc8"
    property var st: backend.state
    property var ov: st.overview || ({})
    property var detail: st.detail || ({})
    property string page: st.page || "Overview"
    property var research: ov.cohorts ? ov.cohorts.research : ({rows:[]})
    property var strategy: ov.cohorts ? ov.cohorts.strategy : ({rows:[]})
    function number(n) { return n === undefined ? "—" : Number(n).toLocaleString(Qt.locale("en_US"), 'f', 0) }
    function dollars(n) { return n === undefined || n === null ? "Unavailable" : "$" + Number(n).toFixed(2) }
    function subtitle() {
        const labels = {Overview:"A clear view of your preserved research universe.", Markets:"Explore snapshot quotes, settlement rules and market history.", Research:"Track A · Human-researched paper forecasts. Never pooled with strategies.", Strategy:"Track B · Frozen flb_v1 paper strategy. Separate evaluation cohort.", Alerts:"Auditor-qualified opportunities only. Historical snapshot, not a live feed.", Positions:"Actual account holdings remain disconnected.", History:"Paper entries from the preserved snapshot. No actual account trades.", Accuracy:"Forecast quality needs resolved outcomes, not just confident estimates.", Evidence:"Provenance, integrity and operational transparency."}
        return labels[page] || ""
    }
    component Txt: Text { color: root.ink; font.family: "Inter"; font.pixelSize: 14; elide: Text.ElideRight }
    component Small: Text { color: root.muted; font.family: "Inter"; font.pixelSize: 12; elide: Text.ElideRight }
    component Panel: Rectangle { color: "#121d2a"; radius: 14; border.color: "#233145"; border.width: 1 }
    component Tag: Rectangle {
        property string label: ""; property color tint: root.accent
        width: tagtext.implicitWidth+22; height: 26; radius: 6; color: Qt.rgba(tint.r,tint.g,tint.b,0.09)
        border.color: Qt.rgba(tint.r,tint.g,tint.b,0.25)
        Text { id: tagtext; anchors.centerIn: parent; text: parent.label; color: parent.tint; font.pixelSize: 11; font.weight: Font.DemiBold }
    }
    component Action: Button {
        id: act; implicitHeight: 34; implicitWidth: 112
        contentItem: Text { text: act.text; color: act.enabled ? root.ink : "#52667f"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { radius: 7; color: act.hovered ? "#263d50" : "#1b2b3d"; border.color: act.activeFocus ? root.accent : "#30465e" }
    }
    component Metric: Panel {
        property string label: ""; property string value: ""; property string note: ""; property color valueColor: root.ink
        implicitHeight: 116
        Column { anchors.fill: parent; anchors.margins: 18; spacing: 9
            Small { text: label; width: parent.width }
            Txt { text: value; font.pixelSize: value.length>14 ? 21 : 28; font.weight: Font.DemiBold; color: valueColor; width: parent.width }
            Small { text: note; font.pixelSize: 11; width: parent.width }
        }
    }
    component Empty: Panel {
        property string heading: ""; property string description: ""; property string badge: "OFFLINE"
        Column { anchors.centerIn: parent; width: Math.min(parent.width-80,640); spacing: 18
            Tag { anchors.horizontalCenter: parent.horizontalCenter; label: badge; tint: "#90a8c4" }
            Txt { text: heading; width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 24; font.weight: Font.DemiBold }
            Text { text: description; color: root.muted; width: parent.width; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 14; lineHeight: 1.45 }
        }
    }
    component PriceChart: Canvas {
        property var points: root.detail.points || []
        onPointsChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var c=getContext('2d'); c.reset(); var left=42, right=width-12, top=14, bottom=height-32
            c.font='11px sans-serif'; c.strokeStyle='#26364a'; c.fillStyle='#8b9eb6'
            if(points.length<2) { c.fillText('No quote history available',left,height/2); return }
            var low=1,high=0
            for(var i=0;i<points.length;i++){low=Math.min(low,points[i].bid);high=Math.max(high,points[i].ask)}
            low=Math.max(0,low-.008);high=Math.min(1,high+.008)
            if(high-low<.01)high=low+.01
            function x(p){return left+(p.t-points[0].t)/Math.max(1,points[points.length-1].t-points[0].t)*(right-left)}
            function y(v){return bottom-(v-low)/(high-low)*(bottom-top)}
            for(var j=0;j<4;j++){var v=low+j*(high-low)/3; c.beginPath();c.moveTo(left,y(v));c.lineTo(right,y(v));c.stroke();c.fillText((v*100).toFixed(1)+'¢',0,y(v)+4)}
            c.beginPath();c.moveTo(x(points[0]),y(points[0].ask));for(i=1;i<points.length;i++)c.lineTo(x(points[i]),y(points[i].ask))
            for(i=points.length-1;i>=0;i--)c.lineTo(x(points[i]),y(points[i].bid));c.closePath();c.fillStyle='#173c46';c.fill()
            for(var k=0;k<2;k++){c.beginPath();c.strokeStyle=k===0?'#55dcc8':'#7e9dff';c.lineWidth=2;for(i=0;i<points.length;i++){var yy=y(k===0?points[i].ask:points[i].bid);if(i===0)c.moveTo(x(points[i]),yy);else c.lineTo(x(points[i]),yy)}c.stroke()}
            c.fillStyle='#8b9eb6';c.fillText('Earlier snapshot',left,height-6);c.fillText('Latest snapshot',Math.max(left,right-100),height-6)
        }
    }
    component ForecastTable: ColumnLayout {
        property var rows: []
        spacing: 0
        RowLayout { Layout.fillWidth: true; Layout.preferredHeight: 36
            Small { text: "MARKET / CONTRACT"; Layout.fillWidth:true }
            Small { text: "SIDE"; Layout.preferredWidth:50 }
            Small { text: "P(YES)"; Layout.preferredWidth:70 }
            Small { text: "FILL"; Layout.preferredWidth:65 }
            Small { text: "QTY"; Layout.preferredWidth:40 }
            Small { text: "P&L"; Layout.preferredWidth:95 }
        }
        Repeater { model: rows
            delegate: Rectangle { required property var modelData; required property int index; Layout.fillWidth:true; Layout.preferredHeight:61; color: index%2===0?'#152333':'#121d2a'; radius:6
                MouseArea { anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:backend.select(parent.modelData.ticker) }
                RowLayout { anchors.fill:parent; anchors.leftMargin:10; anchors.rightMargin:8; spacing:10
                    Column { Layout.fillWidth:true; spacing:5
                        Txt { width:parent.width; text:modelData.ticker; font.pixelSize:12; font.weight:Font.Medium }
                        Small { text:modelData.status; font.pixelSize:11 }
                    }
                    Txt { text:modelData.side.toUpperCase(); color:root.accent; Layout.preferredWidth:50; font.pixelSize:12 }
                    Txt { text:modelData.probability; Layout.preferredWidth:70; font.pixelSize:12 }
                    Txt { text:modelData.price; Layout.preferredWidth:65; font.pixelSize:12 }
                    Txt { text:modelData.qty; Layout.preferredWidth:40; font.pixelSize:12 }
                    Small { text:modelData.pnl_text; Layout.preferredWidth:95 }
                }
            }
        }
    }

    Rectangle { id: sidebar; width:208; anchors.top:parent.top; anchors.bottom:parent.bottom; color:'#0f1824'; border.color:'#203045'
        Column { anchors.fill:parent; anchors.margins:20; spacing:6
            Row { spacing:10; height:72
                Rectangle { width:32;height:32;radius:9;color:'#174b4a'; anchors.verticalCenter:parent.verticalCenter
                    Text { anchors.centerIn:parent;text:'K';font.pixelSize:22;font.weight:Font.Bold;color:root.accent }
                }
                Column { anchors.verticalCenter:parent.verticalCenter;spacing:4
                    Txt { text:'KALSHI';font.pixelSize:17;font.weight:Font.Bold;font.letterSpacing:2 }
                    Small { text:'HUNTER';font.pixelSize:10;font.letterSpacing:3 }
                }
            }
            Small { text:'INTELLIGENCE';font.pixelSize:10;font.letterSpacing:1.5;height:29 }
            Repeater { model:['Overview','Markets','Research','Strategy','Alerts','Positions','History','Accuracy','Evidence']
                delegate: Button { objectName:"nav_"+modelData; required property string modelData; required property int index; width:168;height:44;hoverEnabled:true
                    contentItem: Row { spacing:12
                        Text { text:['◈','▤','◉','◇','△','▣','↗','◎','≡'][index];color:root.page===modelData?root.accent:'#758da8';font.pixelSize:19;width:22;anchors.verticalCenter:parent.verticalCenter }
                        Text { text:modelData;color:root.page===modelData?root.ink:root.muted;font.pixelSize:13;font.weight:root.page===modelData?Font.DemiBold:Font.Normal;anchors.verticalCenter:parent.verticalCenter }
                    }
                    background: Rectangle { radius:8;color:root.page===modelData?'#1b3340':parent.hovered?'#182737':'transparent';border.color:parent.activeFocus?root.accent:'transparent' }
                    onClicked:backend.navigate(modelData)
                }
            }
        }
        Column { anchors.left:parent.left;anchors.right:parent.right;anchors.bottom:parent.bottom;anchors.margins:22;spacing:12
            Tag { label:'OFFLINE SNAPSHOT' }
            Small { text:'No account connected';font.pixelSize:11 }
            Small { text:'Research & paper only';font.pixelSize:11 }
            Small { text:'Phase 2  /  Local desktop';font.pixelSize:10;color:'#627a94' }
        }
    }
    ColumnLayout { anchors.left:sidebar.right;anchors.right:parent.right;anchors.top:parent.top;anchors.bottom:parent.bottom;anchors.margins:28;spacing:18
        RowLayout { Layout.fillWidth:true;Layout.preferredHeight:36
            Small { text:'WORKSPACE  /  '+root.page.toUpperCase();font.letterSpacing:1.2;Layout.fillWidth:true }
            Tag { label:'●  SNAPSHOT ONLY' }
            Tag { label:'ACCOUNT DISCONNECTED';tint:'#96a9c1' }
        }
        RowLayout { Layout.fillWidth:true
            Column { spacing:8;Layout.fillWidth:true
                Txt { text:root.page==='Overview'?'Research overview':root.page; font.pixelSize:30;font.weight:Font.DemiBold }
                Small { text:root.subtitle();width:parent.width;font.pixelSize:13 }
            }
            Column { spacing:6
                Small { text:'PRESERVED AS OF';font.pixelSize:10;font.letterSpacing:1 }
                Txt { text:root.ov.asof || 'Loading snapshot…';font.pixelSize:12 }
            }
        }
        Rectangle { Layout.fillWidth:true;Layout.preferredHeight:38;radius:7;color:'#25251f';border.color:'#44402a'
            Text { anchors.verticalCenter:parent.verticalCenter;anchors.left:parent.left;anchors.leftMargin:14;anchors.right:parent.right;anchors.rightMargin:14;text:'Historical backtests are inconclusive. No demonstrated trading advantage. All quotes shown are archived.';font.pixelSize:12;color:'#d9c28c';elide:Text.ElideRight }
        }
        ScrollView { Layout.fillWidth:true;Layout.fillHeight:true;contentWidth:availableWidth;contentHeight:Math.max(700,availableHeight);clip:true
        Loader { id:content;width:parent.width;height:Math.max(700,parent.height)
            sourceComponent: !root.st.ready ? loadingPage : root.page==='Overview'?overviewPage:root.page==='Markets'?marketsPage:root.page==='Research'||root.page==='Strategy'?forecastsPage:root.page==='Alerts'?alertsPage:root.page==='Positions'?positionsPage:root.page==='History'?historyPage:root.page==='Accuracy'?accuracyPage:evidencePage
        }
        }
        Small { Layout.fillWidth:true;text:root.st.error ? 'ERROR · '+root.st.error : 'READ-ONLY SNAPSHOT     •     NO SCANNER STARTED     •     LOCAL DATA ONLY     •     PAPER ≠ ACTUAL ACCOUNT';font.pixelSize:10;font.letterSpacing:.6;color:root.st.error?'#f18a89':'#738ba5' }
    }
    Component { id:loadingPage;Empty { heading:root.st.error?'Unable to load snapshot':'Loading preserved research';description:root.st.error || 'Reading the isolated snapshot in a background worker.';badge:'READ ONLY' } }
    Component { id:overviewPage
        ColumnLayout { spacing:18
            RowLayout { Layout.fillWidth:true;spacing:14
                Metric { Layout.fillWidth:true;label:'Snapshot market universe';value:root.number((root.ov.counts || {}).markets);note:'Catalog records · may include stale markets' }
                Metric { Layout.fillWidth:true;label:'Track A · Research';value:String(root.research.forecasts_total);note:'Demo-origin paper forecasts';valueColor:root.accent }
                Metric { Layout.fillWidth:true;label:'Track B · Strategy';value:String(root.strategy.forecasts_total);note:'flb_v1 · one shared event';valueColor:'#9cb4ff' }
                Metric { Layout.fillWidth:true;label:'Actual account P&L';value:'Unavailable';note:'No account access authorized';valueColor:root.muted }
            }
            RowLayout { Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:300;spacing:18
                Panel { Layout.fillWidth:true;Layout.fillHeight:true
                    ColumnLayout { anchors.fill:parent;anchors.margins:20;spacing:12
                        RowLayout { Layout.fillWidth:true;Txt { text:'Market history';font.pixelSize:17;font.weight:Font.DemiBold;Layout.fillWidth:true }Tag { label:'ARCHIVED QUOTES';tint:'#92a5bc' } }
                        Small { text:root.detail.ticker || '';Layout.fillWidth:true }
                        PriceChart { Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:130 }
                        RowLayout { Small { text:'● YES ask';color:root.accent }Small { text:'   ● YES bid';color:'#9cb4ff';Layout.fillWidth:true }Small { text:'Spread shaded';font.pixelSize:10 } }
                        Small { text:root.detail.span || '';Layout.fillWidth:true;font.pixelSize:10;Layout.minimumHeight:14 }
                    }
                }
                Panel { Layout.preferredWidth:285;Layout.fillHeight:true
                    ColumnLayout { anchors.fill:parent;anchors.margins:20;spacing:15
                        Txt { text:'Universe composition';font.pixelSize:16;font.weight:Font.DemiBold }
                        Small { text:'Catalog counts by category';font.pixelSize:11 }
                        Repeater { model:(root.ov.categories || []).slice(0,4)
                            delegate:ColumnLayout { required property var modelData; required property int index;Layout.fillWidth:true;spacing:6
                                RowLayout { Small { text:modelData.name;Layout.fillWidth:true }Txt { text:root.number(modelData.count);font.pixelSize:12 } }
                                Rectangle { Layout.fillWidth:true;height:5;radius:2;color:'#26354a';Rectangle { width:parent.width*modelData.count/root.ov.categories[0].count;height:5;radius:2;color:index===0?root.accent:'#6385a8' } }
                            }
                        }
                        Item { Layout.fillHeight:true }
                        Small { text:'';font.pixelSize:11 }
                    }
                }
            }
            Panel { Layout.fillWidth:true;Layout.preferredHeight:285
                ColumnLayout { anchors.fill:parent;anchors.margins:18;spacing:8
                    RowLayout { Txt { text:'Research forecasts';font.pixelSize:16;font.weight:Font.DemiBold;Layout.fillWidth:true }Small { text:'Track A · 3 demo-origin entries' }Action { text:'Open research';onClicked:backend.navigate('Research') } }
                    ForecastTable { Layout.fillWidth:true;rows:root.research.rows }
                }
            }
        }
    }
    Component { id:marketsPage
        RowLayout { spacing:18
            Panel { Layout.fillWidth:true;Layout.fillHeight:true
                ColumnLayout { anchors.fill:parent;anchors.margins:18;spacing:12
                    TextField { id:searchBox;objectName:"market_search";placeholderTextColor:root.muted;Layout.fillWidth:true;placeholderText:'Search all snapshot markets by title or ticker';color:root.ink;selectByMouse:true;font.pixelSize:13;text:root.st.search
                        background:Rectangle { color:'#0d1723';radius:8;border.color:parent.activeFocus?root.accent:'#2e435a' }
                        onTextEdited:searchTimer.restart()
                        Timer { id:searchTimer;interval:300;onTriggered:backend.search(searchBox.text) }
                    }
                    Small { text:root.st.search?'Matching snapshot markets':'Forecast watchlist · search to explore the full catalog';Layout.fillWidth:true }
                    RowLayout { Layout.fillWidth:true;Small { text:'MARKET';Layout.fillWidth:true }Small { text:'YES BID / ASK';Layout.preferredWidth:110 } }
                    ListView { objectName:"market_list"; Layout.fillWidth:true;Layout.fillHeight:true;clip:true;spacing:6;model:root.st.marketRows
                        ScrollBar.vertical:ScrollBar {}
                        delegate:Rectangle { required property var modelData; required property int index;width:ListView.view.width;height:78;radius:8;color:root.detail.ticker===modelData.ticker?'#203b49':'#172535'
                            Column { anchors.left:parent.left;anchors.right:quotes.left;anchors.margins:12;anchors.verticalCenter:parent.verticalCenter;spacing:5
                                Txt { text:modelData.title;width:parent.width;font.pixelSize:12 }
                                Small { text:modelData.ticker;width:parent.width;font.pixelSize:10 }
                                Small { text:modelData.category+' · '+modelData.asof;width:parent.width;font.pixelSize:10 }
                            }
                            Txt { id:quotes;anchors.right:parent.right;anchors.rightMargin:12;anchors.verticalCenter:parent.verticalCenter;width:100;text:modelData.bid+' / '+modelData.ask;color:root.accent;font.pixelSize:12 }
                            MouseArea { anchors.fill:parent;onClicked:backend.select(modelData.ticker);cursorShape:Qt.PointingHandCursor }
                        }
                    }
                    RowLayout { Layout.fillWidth:true;Small { text:root.st.marketRows.length+' shown';Layout.fillWidth:true }Action { text:'Previous';enabled:root.st.offset>0;onClicked:backend.pageMarkets(-1) }Action { text:'Next';enabled:root.st.more;onClicked:backend.pageMarkets(1) } }
                }
            }
            Panel { Layout.preferredWidth:400;Layout.fillHeight:true
                ScrollView { anchors.fill:parent;anchors.margins:20;contentWidth:availableWidth;clip:true
                    ColumnLayout { width:parent.width;spacing:16
                        Tag { label:'MARKET DETAIL' }
                        Text { text:root.detail.title || 'Select a market';Layout.fillWidth:true;wrapMode:Text.WordWrap;color:root.ink;font.pixelSize:21;font.weight:Font.DemiBold }
                        Small { text:root.detail.ticker || '';Layout.fillWidth:true }
                        PriceChart { Layout.fillWidth:true;Layout.preferredHeight:200 }
                        Small { text:root.detail.span || '';Layout.fillWidth:true;font.pixelSize:10;Layout.minimumHeight:14 }
                        Txt { text:'Settlement rules';font.weight:Font.DemiBold }
                        Text { text:root.detail.rules || '';Layout.fillWidth:true;wrapMode:Text.WordWrap;color:root.muted;font.pixelSize:12;lineHeight:1.4 }
                        Small { text:'Snapshot close time: '+(root.detail.close || '—');Layout.fillWidth:true;font.pixelSize:11 }
                    }
                }
            }
        }
    }
    Component { id:forecastsPage
        ColumnLayout { property var cohort:root.page==='Research'?root.research:root.strategy;spacing:18
            RowLayout { Layout.fillWidth:true;spacing:14
                Metric { Layout.fillWidth:true;label:'Paper entries';value:String(parent.parent.cohort.forecasts_total);note:root.page==='Research'?'Demo-origin sourced research':'Frozen flb_v1 strategy';valueColor:root.accent }
                Metric { Layout.fillWidth:true;label:'Resolved outcomes';value:String(parent.parent.cohort.resolved);note:'No inference from unresolved forecasts' }
                Metric { Layout.fillWidth:true;label:'Entry cost incl. recorded fees';value:root.dollars(parent.parent.cohort.cost);note:'Paper cost · not account exposure' }
                Metric { Layout.fillWidth:true;label:'Realized paper P&L';value:root.dollars(parent.parent.cohort.net_pnl);note:'Unavailable until resolved' }
            }
            Panel { Layout.fillWidth:true;Layout.preferredHeight:root.page==='Research'?285:405
                ColumnLayout { anchors.fill:parent;anchors.margins:20;spacing:10
                    RowLayout { Txt { text:root.page==='Research'?'Track A · Research forecasts':'Track B · Strategy forecasts';font.pixelSize:17;font.weight:Font.DemiBold;Layout.fillWidth:true }Tag { label:'PAPER ONLY' } }
                    ForecastTable { Layout.fillWidth:true;rows:parent.parent.parent.cohort.rows }
                    Item { Layout.fillHeight:true }
                }
            }
            Panel { Layout.fillWidth:true;Layout.fillHeight:true
                ScrollView { anchors.fill:parent;anchors.margins:20;contentWidth:availableWidth;clip:true
                    ColumnLayout { width:parent.width;spacing:12
                        Txt { text:root.page==='Research'?'Evidence · '+(root.detail.ticker || 'Select a forecast'):'Pre-registration & correlation';font.pixelSize:17;font.weight:Font.DemiBold }
                        Text { Layout.fillWidth:true;wrapMode:Text.WordWrap;color:root.muted;font.pixelSize:13;lineHeight:1.5
                            text:root.page==='Research'?'Select a forecast row above to inspect its sources and counter-evidence. All three entries came from the original demo research. They are paper forecasts, not accepted trade recommendations. The original uncertainty bands did not support a robust edge. Source records and the appended correction remain preserved.':'The five flb_v1 entries belong to one approval-rating event. They are not five independent experiments. The frozen strategy has zero resolved outcomes in this snapshot; no advantage can be inferred. Actual registration: Oct 21, 2026, 12:00:44 CDT (see preserved errata).'
                        }
                        Repeater { model:root.page==='Research'?(root.detail.research || []):[]
                            delegate:ColumnLayout { required property var modelData; required property int index;Layout.fillWidth:true;spacing:8
                                Small { text:'RESEARCH RECORD #'+modelData.id+' · '+modelData.ticker;Layout.fillWidth:true }
                                Text { text:modelData.method || '';Layout.fillWidth:true;wrapMode:Text.WordWrap;color:root.ink;font.pixelSize:12 }
                                Text { text:modelData.counter_evidence || '';Layout.fillWidth:true;wrapMode:Text.WordWrap;color:root.muted;font.pixelSize:12;lineHeight:1.4 }
                                Repeater { model:modelData.source_list;delegate:Text { required property string modelData; required property int index;text:modelData;Layout.fillWidth:true;wrapMode:Text.WrapAnywhere;color:'#7fb5d6';font.pixelSize:11 } }
                            }
                        }
                    }
                }
            }
        }
    }
    Component { id:alertsPage;Empty { heading:'No qualified alerts in this snapshot';description:'The preserved database contains zero alert records. Forecasts and screened candidates are not automatically qualified opportunities. Live research and notification delivery require a separately approved Phase 3.';badge:'0 PRESERVED ALERTS' } }
    Component { id:positionsPage;Empty { heading:'Your account stays disconnected';description:'Actual Kalshi positions, trade history, equity and account P&L are unavailable. This offline build reads only the preserved research copy. Paper forecasts are never represented as your holdings.';badge:'NO ACCOUNT ACCESS' } }
    Component { id:historyPage
        ScrollView { contentWidth:availableWidth;clip:true
            ColumnLayout { width:parent.width;spacing:18
                Panel { Layout.fillWidth:true;Layout.preferredHeight:285
                    ColumnLayout { anchors.fill:parent;anchors.margins:20;Txt { text:'Track A · Research entry history';font.pixelSize:17 }ForecastTable { Layout.fillWidth:true;rows:root.research.rows } }
                }
                Panel { Layout.fillWidth:true;Layout.preferredHeight:405
                    ColumnLayout { anchors.fill:parent;anchors.margins:20;Txt { text:'Track B · Strategy entry history';font.pixelSize:17 }ForecastTable { Layout.fillWidth:true;rows:root.strategy.rows } }
                }
                Small { text:'Paper settlement P&L = quantity × (side payout − entry price) − recorded entry fee. No outcomes are resolved in this snapshot.';Layout.fillWidth:true }
            }
        }
    }
    Component { id:accuracyPage
        ColumnLayout { spacing:18
            RowLayout { Layout.fillWidth:true;spacing:18
                Empty { Layout.fillWidth:true;Layout.preferredHeight:230;heading:'Track A · Research';description:'3 paper forecasts · 0 resolved\nBrier score, log loss and realized P&L: unavailable.\nNo calibration curve is fabricated.';badge:'INSUFFICIENT OUTCOMES' }
                Empty { Layout.fillWidth:true;Layout.preferredHeight:230;heading:'Track B · Strategy';description:'5 paper forecasts · 0 resolved\nOne correlated event, not five independent samples.\nEvaluated separately from research.';badge:'INSUFFICIENT OUTCOMES' }
            }
            Panel { Layout.fillWidth:true;Layout.fillHeight:true
                ColumnLayout { anchors.fill:parent;anchors.margins:24;spacing:18
                    RowLayout { Txt { text:'Forecast uncertainty at entry';font.pixelSize:18;font.weight:Font.DemiBold;Layout.fillWidth:true }Tag { label:'RESEARCH COHORT ONLY' } }
                    Small { text:'P(YES) · shaded band = researcher uncertainty · dot = estimate. These are not accuracy scores.';Layout.fillWidth:true }
                    Repeater { model:root.research.rows
                        delegate:ColumnLayout { required property var modelData; required property int index;Layout.fillWidth:true;spacing:9
                            RowLayout { Small { text:modelData.ticker;Layout.fillWidth:true }Txt { text:Math.round(modelData.prob_lo*100)+'–'+Math.round(modelData.prob_hi*100)+'%';font.pixelSize:12 } }
                            Rectangle { Layout.fillWidth:true;height:16;radius:5;color:'#1e3044'
                                Rectangle { x:parent.width*modelData.prob_lo;width:parent.width*(modelData.prob_hi-modelData.prob_lo);height:16;radius:4;color:'#285d61' }
                                Rectangle { x:parent.width*modelData.prob_yes-5;y:3;width:10;height:10;radius:5;color:root.accent }
                            }
                        }
                    }
                    RowLayout { Small { text:'0%';Layout.fillWidth:true }Small { text:'100%' } }
                    Item { Layout.fillHeight:true }
                    Text { text:'Historical backtests (legacy Track A) remain a separate, inconclusive archive. Revised label-availability checks identify training rows that must be purged. No historical curve is shown as prospective performance.';Layout.fillWidth:true;wrapMode:Text.WordWrap;color:'#d9c28c';font.pixelSize:12;lineHeight:1.4 }
                }
            }
        }
    }
    Component { id:evidencePage
        RowLayout { spacing:18
            Panel { Layout.fillWidth:true;Layout.fillHeight:true
                ColumnLayout { anchors.fill:parent;anchors.margins:24;spacing:18
                    Txt { text:'Evidence integrity';font.pixelSize:20;font.weight:Font.DemiBold }
                    Text { visible:root.ov.integrity_errors.length>0;text:root.ov.integrity_errors.join('\n');Layout.fillWidth:true;wrapMode:Text.WordWrap;color:'#f18a89';font.pixelSize:12 }
                    Tag { label:root.ov.integrity_errors.length?'VERIFICATION ISSUES':'HASH CHAIN VERIFIED';tint:root.ov.integrity_errors.length?'#e79d8f':root.accent }
                    Repeater { model:[['Protected chain entries',root.ov.counts.hash_chain],['Snapshot observations',root.number(root.ov.counts.snapshots)],['Source research records',root.ov.counts.research],['Unclassified forecasts',root.ov.unknown_forecasts],['Account connection','Disabled'],['Scanner / supervisor','Disabled']]
                        delegate:RowLayout { required property var modelData; required property int index;Layout.fillWidth:true;Small { text:modelData[0];Layout.fillWidth:true }Txt { text:String(modelData[1]);font.pixelSize:13 } }
                    }
                    Text { text:'The desktop reads an isolated copy. Original databases, checkpoints, hashes and independent reviews remain untouched. A valid local hash chain proves internal consistency, not the truth of research or an independently timestamped history.';Layout.fillWidth:true;wrapMode:Text.WordWrap;color:root.muted;font.pixelSize:13;lineHeight:1.5 }
                    Text { text:'Naming map\nNew A: Research forecasts (legacy B/C)\nNew B: Strategy forecasts (legacy C2)\nHistorical backtests: legacy A, separate and inconclusive';Layout.fillWidth:true;wrapMode:Text.WordWrap;color:root.ink;font.pixelSize:13;lineHeight:1.5 }
                    Item { Layout.fillHeight:true }
                }
            }
            Panel { Layout.preferredWidth:390;Layout.fillHeight:true
                ColumnLayout { anchors.fill:parent;anchors.margins:22;spacing:14
                    Txt { text:'Preserved scan history';font.pixelSize:18;font.weight:Font.DemiBold }
                    Small { text:'Historical completions · not current service health' }
                    Repeater { model:root.ov.scans
                        delegate:ColumnLayout { required property var modelData; required property int index;Layout.fillWidth:true;spacing:5
                            RowLayout { Small { text:modelData.time;Layout.fillWidth:true }Tag { label:modelData.status.toUpperCase() } }
                            Small { text:root.number(modelData.markets)+' markets scanned';font.pixelSize:11 }
                            Rectangle { Layout.fillWidth:true;height:1;color:'#28374b' }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
        }
    }
}
