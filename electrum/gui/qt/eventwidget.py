from PyQt5.QtWidgets import (QVBoxLayout, QGridLayout, QLineEdit, QTreeWidgetItem,
                             QHBoxLayout, QPushButton, QScrollArea, QTextEdit, 
                             QFrame, QShortcut, QMainWindow, QCompleter, QInputDialog,
                             QWidget, QMenu, QSizePolicy, QStatusBar, QListView,
                             QAbstractItemView, QSpacerItem, QSizePolicy, QListWidget,QGraphicsDropShadowEffect,
                             QListWidgetItem, QWidget, QLabel,QLayout)
from PyQt5.QtCore import Qt, QRect, QStringListModel, QModelIndex, QItemSelectionModel,QSize
from PyQt5 import QtGui
import time


ODDS_DIVISOR = 10000
POINTS_DIVISOR = 100

class EventWidget(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent=parent)
        self.parent = parent
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0,0,0,0)
        self.grid.setVerticalSpacing(-1)
        self.grid.setHorizontalSpacing(-1)
        self.isEffectiveOdds = self.parent.oddswitch.isChecked()
        
    def btnMoneyLineHomeClicked(self):
        print("Money Line Home button clicked for item : ",self.btnMoneyLineHome.text())
        self.betOutcome = 1
        self.parent.betting_main_widget.add_bet(self)

    def btnMoneyLineAwayClicked(self):
        print("Money Line Away button clicked for item : ",self.btnMoneyLineAway.text())
        self.betOutcome = 2
        self.parent.betting_main_widget.add_bet(self)

    def btnMoneyLineDrawClicked(self):
        print("Money Line Draw button clicked for item : ", self.btnMoneyLineDraw.text())
        self.betOutcome = 3
        self.parent.betting_main_widget.add_bet(self)

    def btnSpreadHomeClicked(self):
        print("Spread Home button clicked for item : ",self.btnSpreadHome.text())
        self.betOutcome = 4
        self.parent.betting_main_widget.add_bet(self)

    def btnSpreadAwayClicked(self):
        print("Spread Away button clicked for item : ",self.btnSpreadAway.text())
        self.betOutcome = 5
        self.parent.betting_main_widget.add_bet(self)

    def btnTotalHomeClicked(self):
        print("Total Home button clicked for item : ",self.btnTotalHome.text())
        self.betOutcome = 6
        self.parent.betting_main_widget.add_bet(self)

    def btnTotalAwayClicked(self):
        print("Total Away button clicked for item : ",self.btnTotalAway.text())
        self.betOutcome = 7
        self.parent.betting_main_widget.add_bet(self)

    
    def setData(self,obj):
        self.eventId = str(obj["event_id"])
        self.lblTournament = QLabel(obj["tournament"] + " " + str("(Event ID: " + str(obj["event_id"]) + ")"))
        self.lblTournament.setStyleSheet("QLabel { background-color : #BD0000;color:#fff;padding:0.5em; font-weight:bold;  }")
        self.lblTournament.setAlignment(Qt.AlignLeft)
        self.lblEventTime = QLabel(time.strftime('%A,%b %dth %I:%M%p(%z %Z)', time.localtime(obj["starting"])))
        self.lblEventTime.setAlignment(Qt.AlignRight)
        self.hbox_tournament = QHBoxLayout()
        self.hbox_tournament.addWidget(self.lblTournament)
        self.hbox_tournament.addWidget(self.lblEventTime)
        self.hbox_tournament.setSpacing(0)
        self.vbox_event = QVBoxLayout()
        self.vbox_event.addLayout(self.hbox_tournament)
        self.lblEventTime.setStyleSheet("QLabel { background-color : #BD0000; color:#fff;padding:0.5em; font-weight:bold; }")
        
        self.lblMoneyLineHeading = QLabel("   Money Line  ")
        self.lblSpreadHeading = QLabel("Spread")
        self.lblTotalHeading = QLabel("Total")
        self.lblDraw = QLabel("Draw")

        
        _moneyLineHomeOdds = obj["odds"][0]["mlHome"]/ODDS_DIVISOR
        _moneyLineAwayOdds = obj["odds"][0]["mlAway"]/ODDS_DIVISOR
        _moneyLineDrawOdds = obj["odds"][0]["mlDraw"]/ODDS_DIVISOR

        if self.isEffectiveOdds :
            _moneyLineHomeOdds = _moneyLineHomeOdds if _moneyLineHomeOdds == 0 else (1 + (_moneyLineHomeOdds - 1) * 0.94)
            _moneyLineAwayOdds = _moneyLineAwayOdds if _moneyLineAwayOdds == 0 else (1 + (_moneyLineAwayOdds - 1) * 0.94)
            _moneyLineDrawOdds = _moneyLineDrawOdds if _moneyLineDrawOdds == 0 else (1 + (_moneyLineDrawOdds - 1) * 0.94)

            
        self.btnMoneyLineHome = QPushButton(str(("{0:.2f}".format(_moneyLineHomeOdds) if str(_moneyLineHomeOdds) != "0.0" else "-")))
        self.btnMoneyLineAway = QPushButton(str(("{0:.2f}".format(_moneyLineAwayOdds) if str(_moneyLineAwayOdds) != "0.0" else "-")))
        self.btnMoneyLineDraw = QPushButton(str(("{0:.2f}".format(_moneyLineDrawOdds) if str(_moneyLineDrawOdds) != "0.0" else "-")))

        self.btnMoneyLineHome.setDisabled(str(_moneyLineHomeOdds) == "0.0")
        self.btnMoneyLineAway.setDisabled(str(_moneyLineAwayOdds) == "0.0")
        self.btnMoneyLineDraw.setDisabled(str(_moneyLineDrawOdds) == "0.0")
        
        

        _spreadPoints = obj["odds"][1]["spreadPoints"]/POINTS_DIVISOR
        _spreadHomeOdds = obj["odds"][1]["spreadHome"]/ODDS_DIVISOR
        _spreadAwayOdds = obj["odds"][1]["spreadAway"]/ODDS_DIVISOR

        if self.isEffectiveOdds :
            _spreadHomeOdds = _spreadHomeOdds if _spreadHomeOdds == 0 else (1 + (_spreadHomeOdds - 1) * 0.94)
            _spreadAwayOdds = _spreadAwayOdds if _spreadAwayOdds == 0 else (1 + (_spreadAwayOdds - 1) * 0.94)
            
    
        self.spreadPoints = str("{0:.2f}".format(_spreadPoints))

        self.spreadPointsAway = ""
        self.spreadPointsHome = ""
        
        if _spreadPoints == 0:
            self.spreadPointsHome =  self.spreadPoints
            self.spreadPointsAway =  self.spreadPoints
        elif _spreadPoints < 0 :
            self.spreadPointsHome = self.spreadPoints
            self.spreadPointsAway = "+ " + str("{0:.2f}".format(abs(_spreadPoints)))
        else:
            self.spreadPointsHome = "+ " + self.spreadPoints
            self.spreadPointsAway = "- " + self.spreadPoints

        self.spreadHomeOdds = str("{0:.2f}".format(_spreadHomeOdds))
        self.spreadAwayOdds = str("{0:.2f}".format(_spreadAwayOdds))
        
        self.btnSpreadHome = QPushButton(self.spreadPointsHome + "    " + self.spreadHomeOdds if self.spreadHomeOdds != "0.00" else "-" )
        self.btnSpreadAway = QPushButton(self.spreadPointsAway + "    " + self.spreadAwayOdds if self.spreadAwayOdds != "0.00" else "-")
        
        
        self.btnSpreadHome.setDisabled(self.spreadHomeOdds == "0.00")
        self.btnSpreadAway.setDisabled(self.spreadAwayOdds == "0.00")
        
        _totalPoints = obj["odds"][2]["totalsPoints"]/POINTS_DIVISOR
        _totalsOverOdds = obj["odds"][2]["totalsOver"]/ODDS_DIVISOR
        _totalsUnderOdds = obj["odds"][2]["totalsUnder"]/ODDS_DIVISOR

        if self.isEffectiveOdds :
            _totalsOverOdds = _totalsOverOdds if _totalsOverOdds == 0 else (1 + (_totalsOverOdds - 1) * 0.94)
            _totalsUnderOdds = _totalsUnderOdds if _totalsUnderOdds == 0 else (1 + (_totalsUnderOdds - 1) * 0.94)
           
        

        self.totalPoints = str("{0:.1f}".format(_totalPoints))
        self.totalsOverOdds = str("{0:.2f}".format(_totalsOverOdds))
        self.totalsUnderOdds = str("{0:.2f}".format(_totalsUnderOdds))

        overTotalPointText = "(O" + self.totalPoints + ")"
        underTotalPointText = "(U" + self.totalPoints + ")"
        
        self.btnTotalHome = QPushButton(overTotalPointText + "    " + self.totalsOverOdds if self.totalsOverOdds != "0.00" else "-" )
        self.btnTotalAway = QPushButton(underTotalPointText + "    " + self.totalsUnderOdds if self.totalsUnderOdds != "0.00" else "-")
        
        self.btnTotalHome.setDisabled(self.totalsOverOdds == "0.00")
        self.btnTotalAway.setDisabled(self.totalsUnderOdds == "0.00")

        self.lblMoneyLineHeading.setAlignment(Qt.AlignHCenter)
        self.lblHomeTeam = QLabel(obj["teams"]["home"])
        self.lblAwayTeam = QLabel(obj["teams"]["away"])
        
        boldFont=QtGui.QFont()
        boldFont.setBold(True)

        self.lblHomeTeam.setAlignment(Qt.AlignLeft)
        self.lblAwayTeam.setAlignment(Qt.AlignLeft)
        self.lblDraw.setAlignment(Qt.AlignLeft)

        self.lblHomeTeam.setFont(boldFont)
        self.lblAwayTeam.setFont(boldFont)
        self.lblDraw.setFont(boldFont)

        self.lblSpreadHeading.setAlignment(Qt.AlignHCenter)
        self.lblTotalHeading.setAlignment(Qt.AlignHCenter)


        self.grid.addWidget(self.lblMoneyLineHeading,0,1)
        self.grid.addWidget(self.lblSpreadHeading,0,2)
        self.grid.addWidget(self.lblTotalHeading,0,3)

        self.grid.addWidget(self.lblHomeTeam,1,0)
        self.grid.addWidget(self.btnMoneyLineHome,1,1,alignment=Qt.AlignCenter)
        self.grid.addWidget(self.btnSpreadHome,1,2,alignment=Qt.AlignCenter)
        self.grid.addWidget(self.btnTotalHome,1,3,alignment=Qt.AlignCenter)

        self.grid.addWidget(self.lblAwayTeam,2,0)
        self.grid.addWidget(self.btnMoneyLineAway,2,1,alignment=Qt.AlignCenter)
        self.grid.addWidget(self.btnSpreadAway,2,2,alignment=Qt.AlignCenter)
        self.grid.addWidget(self.btnTotalAway,2,3,alignment=Qt.AlignCenter)

        self.grid.addWidget(self.lblDraw,3,0)
        self.grid.addWidget(self.btnMoneyLineDraw,3,1,alignment=Qt.AlignCenter)
        #self.grid.addWidget(self.spreaddraw,3,2,alignment=Qt.AlignCenter)
        #self.grid.addWidget(self.totaldraw,3,3,alignment=Qt.AlignCenter)
        self.btnMoneyLineHome.clicked.connect(self.btnMoneyLineHomeClicked)
        self.btnMoneyLineAway.clicked.connect(self.btnMoneyLineAwayClicked)
        self.btnMoneyLineDraw.clicked.connect(self.btnMoneyLineDrawClicked)
        
        self.btnSpreadHome.clicked.connect(self.btnSpreadHomeClicked)
        self.btnSpreadAway.clicked.connect(self.btnSpreadAwayClicked)
        
        self.btnTotalHome.clicked.connect(self.btnTotalHomeClicked)
        self.btnTotalAway.clicked.connect(self.btnTotalAwayClicked)

        self.h_box_event = QHBoxLayout()
        self.h_box_event.addLayout(self.grid)
        self.h_box_event.setContentsMargins(10,10,10,10)
        self.vbox_event.setContentsMargins(0,0,0,0)
        
        self.vbox_event.addLayout(self.h_box_event)
        self.setLayout(self.vbox_event)
        self.setStyleSheet(
            "QPushButton {"
            "font-weight:bold;"
            "}"
            )