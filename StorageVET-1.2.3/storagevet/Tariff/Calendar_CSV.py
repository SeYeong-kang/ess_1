"""
Copyright (c) 2023, Electric Power Research Institute

 All rights reserved.

 Redistribution and use in source and binary forms, with or without modification,
 are permitted provided that the following conditions are met:

     * Redistributions of source code must retain the above copyright notice,
       this list of conditions and the following disclaimer.
     * Redistributions in binary form must reproduce the above copyright notice,
       this list of conditions and the following disclaimer in the documentation
       and/or other materials provided with the distribution.
     * Neither the name of DER-VET nor the names of its contributors
       may be used to endorse or promote products derived from this software
       without specific prior written permission.

 THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
 CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
 LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
 NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
 SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import requests
import pprint
import Period as period
import EnergyTier as et
import csv
import os, sys
import pandas as pd

USERS_OPENEI_API_KEY = ''  # 변수 초기화 및 빈 문자열 할당
ADDRESS = '3420 Hillview Ave, Palo Alto, CA 94304'
LIMIT = 20

#전기요금 정보 가져와 처리
class API:
    def __init__(self):
     # OpenEI API 엔드포인트 URL (컴퓨터 네트워크에 연결하고 컴퓨터 네트워크와 정보를 교환하는 물리적 디바이스)
        self.URL = "https://api.openei.org/utility_rates"
         
    #API 요청에 사용될 매개변수들을 정의    
        self.PARAMS = {'version': 5, 'api_key': USERS_OPENEI_API_KEY, 'format': 'json',
                       'address': ADDRESS, 'limit': LIMIT}
        

      # OpenEI API에 GET 요청을 보내고 응답을 저장
        self.r = requests.get(url=self.URL, params=self.PARAMS)
     # 응답을 JSON 형식으로 파싱하여 데이터 속성에 저장
        self.data = self.r.json()
      # 에러가 응답에 포함되어 있다면 예외 발생
        if 'error' in self.data.keys():
            raise Exception(f'\nBad API call: {self.data["error"]}')
      # 임시 및 최종 결과 파일의 파일명
        self.temp_file = "tariff_temp.csv"
        self.new_file = "tariff.csv"
     
      # 다양한 데이터 구조를 저장하는 속성들
        self.tariff = None
        self.energyratestructure = []
        self.energyweekdayschedule = []
        self.energyweekendschedule = []
        self.energy_period_list = []
     
     # 요금과 관련된 정보를 저장하는 속성들
        self.max = None
        self.rate = None
        self.unit = None
        self.adj = None
        self.sell = None
     
       # 날짜 목록을 저장하는 속성들
        self.weekday_date_list = []
        self.weekend_date_list = []
        self.date_list = []

       # CSV 파일의 헤더 열을 정의하는 리스트
        self.header = ['Period', 'Tier 1 Max', 'Tier 1 Rate',
                                 'Tier 2 Max', 'Tier 2 Rate',
                                 'Tier 3 Max', 'Tier 3 Rate',
                                 'Tier 4 Max', 'Tier 4 Rate',
                                 'Tier 5 Max', 'Tier 5 Rate',
                                 'Tier 6 Max', 'Tier 6 Rate',
                                 'Tier 7 Max', 'Tier 7 Rate',
                                 'Tier 8 Max', 'Tier 8 Rate']

    def print_all(self):
        """
        Prints necessary identifying information of all tariffs that show from result page on OpenEI
        #OpenEI API 결과페이지에서 표시된 모든 전력 요금에 대한 필수 식별정보를 출   
        """

     # 초기 카운트 값을 1로 설정
        count = 1
     # OpenEI API 응답에서 "items"를 반복하여 각각의 요금 정보를 출력
        for item in self.data["items"]:
            print("---------------------------------------------------", count)
         # Utility 정보 출력
            print("Utility.......", item["utility"])
         # Name 정보 출력
            print("Name..........", item["name"])

         # End Date 정보가 있으면 출력
            if "enddate" in item:
                print("End Date......", item["enddate"])

         # Start Date 정보가 있으면 출력
            if "startdate" in item:
                print("Start Date....", item["startdate"])

          # EIA ID 정보 출력
            print("EIA ID........", item["eiaid"])
         # URL 정보 출력
            print("URL...........", item["uri"])

         # Description 정보가 있으면 출력
            if "description" in item:
                print("Description...", item["description"])
            print(" ")
         # 카운트 증가 (몇 번째 전기 요금인지 나타내기 위해)
            count += 1

    def reset(self):
        """
        Resets tariff's tier values to None; necessary for print_index

        """

     # print_index 메서드 호출 전 전력 요금의 티어(층) 값들을 None으로 초기화하여 새로운 인덱스를 출력하기 전 값들이 올바르게 초기화되도록 함.
        self.max = None
        self.rate = None
        self.unit = None
        self.adj = None
        self.sell = None

    def print_index(self, index):
        """
        Establishes all periods and tiers of the tariff using period and tier objects

        Args:
            index (Int): user input for which tariff they choose

        """

     # 입력된 인덱스가 유효한 범위 내에 있는지 확인
        i = index
        while i not in range(1, LIMIT + 1): # 상단 limit = 20
            print('That index is out of range, please try another...')
            i = int(input("Which tariff would you like to use?..."))
        label = self.data["items"][i - 1]["label"]
        params = {'version': 5, 'api_key': USERS_OPENEI_API_KEY, 'format': 'json', 'getpage': label, 'detail': 'full'}
        r = requests.get(url=self.URL, params=params)
        self.tariff = r.json()

        if "energyratestructure" in self.tariff["items"][0]:
            self.energyratestructure = self.tariff["items"][0]["energyratestructure"]
            pcount = 1  # period count
            tcount = 1  # tier count
            for p in self.energyratestructure:
                self.energy_period_list.append(period.Period(pcount))
                for i in p:
                    if "max" in i:
                        self.max = i["max"]

                    if "rate" in i:
                        self.rate = i["rate"]

                    if "unit" in i:
                        self.unit = i["unit"]

                    if "adjustment" in i:
                        self.adj = i["adjustment"]

                    if "sell" in i:
                        self.sell = i["sell"]

                    self.energy_period_list[pcount - 1].add(et.Tier(tcount, self.max, self.rate, self.unit, self.adj, self.sell))
                    tcount += 1
                    self.reset()
                tcount = 1
                pcount += 1

    def energy_structure(self):
        """
        Prints energy structure, month and hour schedule of when every period is active, to terminal

        """
        self.energyweekdayschedule = self.tariff["items"][0]["energyweekdayschedule"]
        self.energyweekendschedule = self.tariff["items"][0]["energyweekendschedule"]
        for year in self.energyweekdayschedule:
            count = 0
            for month in year:
                year[count] = month + 1
                count += 1
        for year in self.energyweekendschedule:
            count = 0
            for month in year:
                year[count] = month + 1
                count += 1

    def calendar(self):
        """
        Makes a csv file with weekday schedule, weekend schedule, and the rates of each period

        """
        with open(self.temp_file, "w", newline='') as csvfile:
            tariff_writer = csv.writer(csvfile)
            count = 0
            hours = [" ", 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
            months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

            tariff_writer.writerow(hours)
            for i in self.energyweekdayschedule:
                i.insert(0, months[count])
                tariff_writer.writerow(i)
                count += 1

            tariff_writer.writerow(" ")
            tariff_writer.writerow(" ")
            tariff_writer.writerow(" ")

            count = 0
            tariff_writer.writerow(hours)
            for i in self.energyweekendschedule:
                i.insert(0, months[count])
                tariff_writer.writerow(i)
                count += 1

            tariff_writer.writerow(" ")
            tariff_writer.writerow(" ")
            tariff_writer.writerow(" ")

            tariff_writer.writerow(self.header)
            for period in self.energy_period_list:
                row = [period.number]
                for tier in period.tier_list:
                    row.append(tier.max)
                    row.append(tier.rate)
                tariff_writer.writerow(row)

    def read_csv(self):
        """
        Reads the csv file back and creates three data frames based on weekday schedule, weekend schedule, and periods

        """
        with open(self.temp_file, 'r') as inp, open(self.new_file, "w") as out:
            writer = csv.writer(out)
            for row in csv.reader(inp):
                if ''.join(row).strip():  # https://stackoverflow.com/questions/18890688/how-to-skip-blank-line-while-reading-csv-file-using-python/54381516
                    writer.writerow(row)
        os.remove(self.temp_file)
        text = pd.read_csv(self.new_file)

        # weekday schedule
        print("============================")
        print("DF_WEEKDAY")
        weekday_df = text[:12]
        print(weekday_df)
        print("\n")

        # weekend schedule
        print("DF_WEEKEND")
        weekend_df = text[13:25]
        weekend_df.reset_index(drop=True, inplace=True)
        print(weekend_df)
        print("\n")

        # periods and tiers
        print("DF_PERIODS")
        periods_df = text[25:]

        # rename header to period header
        header = periods_df.iloc[0]
        periods_df = periods_df[1:]
        periods_df = periods_df.rename(columns=header)

        # reset index to start at 0
        periods_df.reset_index(drop=True, inplace=True)

        # remove all columns that are nan
        periods_df = periods_df.loc[:, periods_df.columns.notnull()]
        print(periods_df)
        print("\n")

    def run(self):
        """
        Runs the program utilizing the functions

        """
        self.print_all()
        i = int(input("Which tariff would you like to use?..."))
        self.print_index(i)
        self.energy_structure()
        self.calendar()
        # in Windows os, you can edit the spreadsheet here first
        if sys.platform.startswith('win'):
            os.startfile(self.temp_file)
            response = input("Type 'ready' when you are done editing the excel file...")
            while response != "ready":
                response = input("Type 'ready' when you are done editing the excel file...")
        self.read_csv()


def main():
    api = API()
    api.run()


if __name__ == "__main__": main()
