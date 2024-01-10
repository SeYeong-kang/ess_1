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
"""
Backup.py

This Python class contains methods and attributes specific for service analysis within StorageVet.
"""
from storagevet.ValueStreams.ValueStream import ValueStream
from storagevet.SystemRequirement import Requirement
import storagevet.Library as Lib
import pandas as pd
import numpy as np

# 백업 전력 서비스에 대한 구체적인 동작 정의
class Backup(ValueStream):
    """ Backup Power Service. Each service will be daughters of the ValueStream class.

    """

    def __init__(self, params):
        """ Generates the objective function, finds and creates constraints.

          Args:
            params (Dict): input parameters
        """

        # generate the generic service object
        # ValueStream 클래스의 생성자를 호출하여 부모 클래스의 초기화를 수행
        # 이 때, 'Backup'이라는 서비스 타입과 입력된 매개변수(params)를 전달
        ValueStream.__init__(self, 'Backup', params)
        # 해당 키에 해당하는 값 가져옴
        self.energy_req = params['daily_energy']
        self.monthly_energy = params['monthly_energy']  # raw input form of energy requirement
        self.price = params['monthly_price']

    def grow_drop_data(self, years, frequency, load_growth):
   """
    주어진 데이터를 성장시키거나 불필요한 데이터를 삭제하는 메서드입니다.
    성장 데이터를 추가한 후에는 최적화를 실행하기 전에 이 메서드를 호출해야 합니다.

    Args:
        years (List): 분석이 진행될 연도 목록입니다.
        frequency (str): 시계열 데이터의 주기입니다.
        load_growth (float): 시뮬레이션에서의 부하 성장률을 나타내는 퍼센트 또는 소수값입니다.

    """

        # 일일 에너지 요구량에 대한 데이터 성장 및 불필요한 데이터 삭제
        # self.energy_req에 대한 데이터를 성장시키는 역할
        # 해당 함수는 주어진 연도(years), 초기값(0), 주기(frequency)에 따라 데이터를 성장
        self.energy_req = Lib.fill_extra_data(self.energy_req, years, 0, frequency)
        self.energy_req = Lib.drop_extra_data(self.energy_req, years)

        # 월간 에너지 요구량에 대한 데이터 성장 및 불필요한 데이터 삭제
        self.monthly_energy = Lib.fill_extra_data(self.monthly_energy, years, 0, 'M')
        self.monthly_energy = Lib.drop_extra_data(self.monthly_energy, years)

         # 월간 에너지 요구량에 대한 데이터 성장 및 불필요한 데이터 삭제
        self.price = Lib.fill_extra_data(self.price, years, 0, 'M')
        self.price = Lib.drop_extra_data(self.price, years)

    def calculate_system_requirements(self, der_lst):
        """ Calculate the system requirements that must be meet regardless of what other value streams are active
        However these requirements do depend on the technology that are active in our analysis

        Args:
            der_lst (list): list of the initialized DERs in our scenario

        """
        # backup energy adds a minimum energy level
        self.system_requirements.append(Requirement('energy', 'min', self.name, self.energy_req))

    def monthly_report(self):
        """  Calculates the monthly cost or benefit of the service and adds them to the monthly financial result dataframe

        Returns: A dataframe with the monthly input price of the service and the calculated monthly value in respect
                for each month

        """
     
        # 월간 재무 결과 데이터프레임 초기화
        monthly_financial_result = pd.DataFrame({'Backup Price ($/kWh)': self.price}, index=self.price.index)
       # 데이터 프레임의 인덱스에 'Year-Month'라는 이름을 부여
        monthly_financial_result.index.names = ['Year-Month']

        return monthly_financial_result

    def proforma_report(self, opt_years, apply_inflation_rate_func, fill_forward_func, results):
        """ Calculates the proforma that corresponds to participation in this value stream

        Args:
            opt_years (list): list of years the optimization problem ran for
            apply_inflation_rate_func:
            fill_forward_func:
            results (pd.DataFrame): DataFrame with all the optimization variable solutions

        Returns: A tuple of a DateFrame (of with each year in opt_year as the index and the corresponding
        value this stream provided)

        """
        # 부모 클래스(ValueStream)의 proforma_report 메서드 호출
        proforma = ValueStream.proforma_report(self, opt_years, apply_inflation_rate_func,
                                               fill_forward_func, results)
        # DataFrame인 proforma에 self.name이라는 열(column)을 추가하고 해당 열에 0 값을 할당
        proforma[self.name] = 0

        # 각 연도에 대한 월간 혜택 계산
        for year in opt_years:
           # np.multiply는 NumPy 라이브러리의 원소별 곱셈 함수
            monthly_benefit = np.multiply(self.monthly_energy, self.price)
           # df.loc[row_label, column_label]와 같은 형식으로 사용
           # 행과 열을 지정하여 데이터를 추출
            proforma.loc[pd.Period(year=year, freq='y')] = monthly_benefit.sum()
        # apply inflation rates
        '''
        이 코드는 apply_inflation_rate_func 함수를 사용하여 proforma DataFrame의 값에 인플레이션 비율을 적용하는 역할 
        여기서 apply_inflation_rate_func 함수에는 세 개의 인자가 전달.

        첫 번째 인자: 적용할 DataFrame인 proforma.
        두 번째 인자: 여기서는 None으로 전달되었으며, apply_inflation_rate_func 함수가 해당 인자에 따라 동작
        세 번째 인자: 최소 연도(min(opt_years))로, 인플레이션 비율을 적용할 기준 연도를 나타냄
        '''
        proforma = apply_inflation_rate_func(proforma, None, min(opt_years))

        return proforma

    def timeseries_report(self):
        """ Summaries the optimization results for this Value Stream.

        Returns: A timeseries dataframe with user-friendly column headers that summarize the results
            pertaining to this instance

        """
        # timeseries 데이터프레임 초기화
        # pd.DataFrame은 빈 데이터프레임을 생성하는데 사용
        report = pd.DataFrame(index=self.energy_req.index)
        # 'Backup Energy Reserved (kWh)' 열에 energy_req 값을 할당
        report.loc[:, 'Backup Energy Reserved (kWh)'] = self.energy_req
        return report

    def update_price_signals(self, monthly_data, time_series_data):
        """ Updates attributes related to price signals with new price signals that are saved in
        the arguments of the method. Only updates the price signals that exist, and does not require all
        price signals needed for this service.

        Args:
            monthly_data (DataFrame): monthly data after pre-processing
            time_series_data (DataFrame): time series data after pre-processing

        """
        try:
             # 'Backup Price ($/kWh)' 열이 있는 경우 해당 열의 값을 self.price에 할당
            self.price = monthly_data.loc[:, 'Backup Price ($/kWh)']
        except KeyError:
            # 'Backup Price ($/kWh)' 열이 없는 경우 예외 처리
            pass
