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
'''
 OpenEI(Open Energy Information) API를 활용하여 주소에 대한 전력 요금 정보를 가져와 처리하는 프로그램. 
 코드의 주요 목표는 사용자에게 전력 요금과 관련된 정보를 제공하고, 해당 정보를 활용하여 CSV 파일에 스케줄 및 기간/티어별 요금 정보를 작성
 '''
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
        #OpenEI API 결과페이지에서 표시된 모든 전력 요금에 대한 필수 식별정보를 출력력   
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
     # 조건 범위에 있지 않는 동안 루프가 반복해서 실행
        while i not in range(1, LIMIT + 1): 
            print('That index is out of range, please try another...')
            i = int(input("Which tariff would you like to use?..."))

       # 선택한 인덱스에 해당하는 전력 요금의 레이블을 가져옴
       # "items"의 목록에서 특정 인덱스 'i-1'에 해당하는 요소 선택 후 그 요소에서 "label"이라는 속성 선택
        label = self.data["items"][i - 1]["label"]
     # API를 통해 선택한 전력 요금에 대한 상세 정보를 가져옴
        params = {'version': 5, 'api_key': USERS_OPENEI_API_KEY, 'format': 'json', 'getpage': label, 'detail': 'full'}
        r = requests.get(url=self.URL, params=params)
        self.tariff = r.json()

      # 전력 요금 구조에 "energyratestructure"가 있는 경우 해당 정보를 설정
        if "energyratestructure" in self.tariff["items"][0]: #items에서 첫번째 요소 선택
            self.energyratestructure = self.tariff["items"][0]["energyratestructure"]
            pcount = 1  # period count
            tcount = 1  # tier count
         # 각 기간(period)에 대해 반복
            for p in self.energyratestructure:
             # 전력 요금의 기간 객체를 생성하고 리스트에 추가
                self.energy_period_list.append(period.Period(pcount))

              # 각 티어에 대해 반복
                for i in p:
                 #"max" 키가 존재할경우 'self.max'에 해당 값 할당당
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

                   # 티어 객체를 생성하고 현재 기간에 추가
                   # et.Tier 클래스의 인스턴스를 생성.(객체)
                   #pcount - 1 에 해당하는 위치에 et.Tier 추가 
                    self.energy_period_list[pcount - 1].add(et.Tier(tcount, self.max, self.rate, self.unit, self.adj, self.sell))
                    tcount += 1
                 # 속성 초기화
                    self.reset()
                tcount = 1
                pcount += 1

    def energy_structure(self):
        """
        Prints energy structure, month and hour schedule of when every period is active, to terminal

        """
       # 주중 및 주말의 에너지 스케줄을 가져옴
        self.energyweekdayschedule = self.tariff["items"][0]["energyweekdayschedule"]
        self.energyweekendschedule = self.tariff["items"][0]["energyweekendschedule"]
        
     # 주중 스케줄에 대한 처리
       for year in self.energyweekdayschedule:
            count = 0
            # 각 월에 대한 처리
            for month in year:
               # 각 월의 값에 1을 더함
                year[count] = month + 1
                count += 1
         # 주말 스케줄에 대한 처리
        for year in self.energyweekendschedule:
            count = 0
           # 각 월에 대한 처리
            for month in year:
               # 각 월의 값에 1을 더함
                year[count] = month + 1
                count += 1

    def calendar(self):
        """
        Makes a csv file with weekday schedule, weekend schedule, and the rates of each period

        """
       # 주중 및 주말 스케줄, 시간 및 월을 나타내는 데이터 정의
       # self.temp_file 파일을 쓰기 모드("w")로 열기
       # newline=''은 CSV 파일에서 빈 줄을 추가하지 않도록 하는 옵션
        with open(self.temp_file, "w", newline='') as csvfile:
          # csvfile을 csv.writer 객체로 생성하여 데이터를 CSV 형식으로 쓰기 위한 준비
          # 이 객체를 사용하여 데이터를 파일에 쓸 수 있습니다.
          # with 문을 사용해 해당 파일 객체를 반환. / with 블록을 나갈 때, 파일이 자동으로 닫힘. 
            tariff_writer = csv.writer(csvfile)
            count = 0
            hours = [" ", 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
            months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

          # 헤더로 시간 정보를 추가
          # tariff_writer를 사용하여 CSV 파일에 한 행을 작성하는 코드
            tariff_writer.writerow(hours)
         # 주중 스케줄에 대한 처리
            for i in self.energyweekdayschedule:
                # 현재 처리 중인 i 리스트(하나의 월에 대한 데이터)의 첫 번째 위치(인덱스 0)에 해당 월의 이름을 추가합니다. 
                # months 리스트에서 count 인덱스에 있는 월의 이름이 추가
                i.insert(0, months[count])
                # CSV 파일에 현재 처리 중인 데이터를 작성합니다. 이때, 월의 이름이 추가된 상태로 한 행으로 작성
                tariff_writer.writerow(i)
                # 다음 월의 이름을 처리하기 위해 count 변수를 증가
                count += 1

           # 공백 라인 추가
            tariff_writer.writerow(" ")
            tariff_writer.writerow(" ")
            tariff_writer.writerow(" ")

            count = 0
             # 다시 헤더로 시간 정보를 추가
            tariff_writer.writerow(hours)
           # 주말 스케줄에 대한 처리
            for i in self.energyweekendschedule:
                i.insert(0, months[count])
                tariff_writer.writerow(i)
                count += 1

           # 공백 라인 추가
            tariff_writer.writerow(" ")
            tariff_writer.writerow(" ")
            tariff_writer.writerow(" ")

           # 각 기간의 요금 정보를 추가
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
         #CSV 파일 (self.temp_file)을 읽기용으로 열고
            for row in csv.reader(inp):
                if ''.join(row).strip():  # https://stackoverflow.com/questions/18890688/how-to-skip-blank-line-while-reading-csv-file-using-python/54381516
                 # 입력 CSV 파일의 각 행을 반복하며 비어 있지 않은 행을 새 파일에 작성
                    writer.writerow(row)
        # 임시 파일 (self.temp_file)을 제거
        os.remove(self.temp_file)
        # Pandas 데이터 프레임(text)으로 읽어짐.
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
        # Datafram의 인덱스 재설정
        # drop = True >> 현재의 인덱스를 삭제
        # inplace = True >> DataFrame 자체를 수정하고 반환하지 않음.
        # 즉 weekend_df의 인덱스를 0부터 시작하여 재설정하고 이를 Dataframe에 적용
        weekend_df.reset_index(drop=True, inplace=True)
        print(weekend_df)
        print("\n")

        # periods and tiers
        print("DF_PERIODS")
        periods_df = text[25:]

        # rename header to period header
        #iloc은 정수 위치를 기반으로 DataFrame에서 행을 선택하는 메서드
        header = periods_df.iloc[0]
        #첫 번째 행을 제외한 모든 행 선택택 
        periods_df = periods_df[1:]
        # 열 이름 변경
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

# 다른 모듈에 의해 임포트 될 때 실행 안됨
if __name__ == "__main__": main()
