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
DemandChargeReduction.py

This Python class contains methods and attributes specific for service analysis within StorageVet.
"""
from storagevet.ValueStreams.ValueStream import ValueStream
import numpy as np
import cvxpy as cvx
import pandas as pd
import sys
from storagevet.Finances import Financial
from storagevet.ErrorHandling import *
import copy
import time

SATURDAY = 5


class DemandChargeReduction(ValueStream):
    """ Retail demand charge reduction. A behind the meter service.
        소매 수요 요금 감소. 계량기 뒤의 서비스입니다.
    """

    def __init__(self, params):
        """ Generates the objective function, finds and creates constraints.

        Args:
            params (Dict): input parameters
        """
        ValueStream.__init__(self, 'DCM', params)
        # self.demand_rate = params['rate'] 

        # params 딕셔너리에서 'tariff' 키에 해당하는 값을 가져와서 self.tariff 속성에 할당하는 역할
        self.tariff = params['tariff'] # 전기 요금 체계
        self.billing_period = params['billing_period']# 청구 주기
        self.growth = params['growth']/100 # 수요 예측 성장률

        self.billing_period_bill = pd.DataFrame() # 청구 주기별 요금
        self.monthly_bill = pd.DataFrame() # 월별 요금

    def grow_drop_data(self, years, frequency, load_growth):
        """ Adds data by growing the given data OR drops any extra data that might have slipped in.
        Update variable that hold timeseries data after adding growth data. These method should be called after
        add_growth_data and before the optimization is run.

        Args:
            years (List): list of years for which analysis will occur on
            frequency (str): period frequency of the timeseries data
            load_growth (float): percent/ decimal value of the growth rate of loads in this simulation

        This function adds billing periods to the tariff that match the given year's structure, but the values have
        a growth rate applied to them. Then it lists them within self.billing_period.

        """
        # 현재 데이터에 대한 연도 가져오기
        data_year = self.billing_period.index.year.unique()
        # 누락된 데이터가 있는 연도 확인
        # years 리스트에 있는 연도를 Period 형태로 변환하여 set으로 만드는 코드
        # 두 개의 set에 대해 - 연산을 수행하면, 첫 번째 set에는 포함되지만 두 번째 set에는 포함되지 않는 연도들의 set을 얻게 됨.
        no_data_year = {pd.Period(year) for year in years} - {pd.Period(year) for year in data_year}  # which years do we not have data for

        # 누락된 데이터가 있는 경우
        if len(no_data_year) > 0:
            for yr in no_data_year:
                # 누락된 데이터가 있는 연도에서 기존 데이터의 소스 연도 가져오기
                source_year = pd.Period(max(data_year))
             
                # 연도 간의 차이 계산
                years = yr.year - source_year.year

                first_day = '1/1/' + str(yr.year) # 각 연도의 1월 1일을 시작일로 설정
                last_day = '1/1/' + str(yr.year + 1) # 각 연도의 1월 1일을기준으로 다음 연도의 1월1일 전날인 마지막일로 설정 

                # 새로운 인덱스 생성
                new_index = pd.date_range(start=first_day, end=last_day, freq=frequency, closed='left')
                size = new_index.size

                # make new tariff with charges that have increase with user-defined growth rate
                add_tariff = self.tariff.reset_index()
                add_tariff.loc[:, 'Value'] = self.tariff['Value'].values*(1+self.growth)**years
                add_tariff.loc[:, 'Billing Period'] = self.tariff.index + self.tariff.index.max()
                add_tariff = add_tariff.set_index('Billing Period', drop=True)
                # Build Energy Price Vector based on the new year
                temp = pd.DataFrame(index=new_index)
                
               # new_index.weekday는 Pandas에서 시간 인덱스의 각 날짜가 무슨 요일인지 나타내는 속성입니다. 
               # 반환되는 값은 각 요일에 대한 정수로, 월요일부터 일요일까지 0부터 6까지의 값을 가집
                weekday = new_index.weekday
                # Timedelta : 시간 간격을 나타내는 객체
                # hour : 시간 데이터에서 시간 부분만 추출하는 속성
                he = (new_index + pd.Timedelta('1s')).hour + 1

                # range(size) 횟수만큼 빈 리스트를 갖는 리스트가 생성
                billing_period = [[] for _ in range(size)]

                for p in add_tariff.index:
                    # edit the pricedf energy price and period values for all of the periods defined
                    # in the tariff input file
                    bill = add_tariff.loc[p, :]
                    # temp.index.month: 인덱스의 월 정보를 나타내는 배열
                    # he: 시간 정보를 나타내는 배열로, +1이 더해진 값을 사용
                    mask = Financial.create_bill_period_mask(bill, temp.index.month, he, weekday)
                    # lower : 소문자로 환
                    if bill['Charge'].lower() == 'demand':
                        # enumerate 함수는 순회 가능한(iterable) 객체(리스트, 튜플, 문자열 등)를 입력으로 받아 인덱스와 해당 요소를 순회하는 데 사용
                        for i, true_false in enumerate(mask):
                            if true_false:
                                billing_period[i].append(p)
                billing_period = pd.Series(billing_period, dtype='object', index=temp.index)

                # ADD CHECK TO MAKE SURE ENERGY PRICES ARE THE SAME FOR EACH OVERLAPPING BILLING PERIOD
                # Check to see that each timestep has a period assigned to it
                if not billing_period.apply(len).all():
                    TellUser.error('The billing periods in the input file do not partition the year. '
                                   + 'Please check the tariff input file')
                    # 용자 정의 예외인 TariffError를 발생
                    raise TariffError('The billing periods in the input file do not partition the year')

                # 기존 tariff 및 billing_period에 새로운 데이터 추가
                # pandas 라이브러리의 함수로, 여러 DataFrame을 이어붙이는(concatenating) 데 사용됨.
                # self.tariff DataFrame과 add_tariff DataFrame을 이어붙이고, sort=True 옵션을 통해 결과 DataFrame을 인덱스를 기준으로 정렬하라는 의미
                self.tariff = pd.concat([self.tariff, add_tariff], sort=True)
                self.billing_period = pd.concat([self.billing_period, billing_period], sort=True)

    def objective_function(self, mask, load_sum, tot_variable_gen, generator_out_sum, net_ess_power, annuity_scalar=1):
        """ Generates the full objective function, including the optimization variables.
            전체 목적 함수를 생성하고 최적화 변수를 포함
        Args:
            mask (DataFrame): A boolean array that is true for indices corresponding to time_series data included
                in the subs data set
            tot_variable_gen (Expression): the sum of the variable/intermittent generation sources
            load_sum (list, Expression): the sum of load within the system
            generator_out_sum (list, Expression): the sum of conventional generation within the system
            net_ess_power (list, Expression): the sum of the net power of all the ESS in the system. [= charge - discharge]
            annuity_scalar (float): a scalar value to be multiplied by any yearly cost or benefit that helps capture the cost/benefit over
                        the entire project lifetime (only to be set iff sizing)

        Returns:
            A dictionary with the portion of the objective function that it affects, labeled by the expression's key. Default is to return {}.
        """
        # 함수의 어떤 부분이 실행되는 데 얼마나 시간이 걸리는지 확인하고자 할 때 사용됩니다.
        start = time.time()
        total_demand_charges = 0
        net_load = load_sum + net_ess_power + (-1)*generator_out_sum + (-1)*tot_variable_gen
        sub_billing_period = self.billing_period.loc[mask]
        # 월별로 수요 요금을 결정하고 추가
        months = sub_billing_period.index.to_period('M')
        # unique() 함수는 배열 또는 시퀀스에서 중복된 값을 제거하고 고유한 값을 반환하는 함수
        for mo in months.unique():
            # 해당 월에 대한 불리언 배열; 선택된 월에 대해 True
            monthly_mask = (sub_billing_period.index.month == mo.month)

            # select the month's billing period data
            month_sub_billing_period = sub_billing_period.loc[monthly_mask]

            # set of unique billing periods in the selected month
            pset = {item for sublist in month_sub_billing_period for item in sublist}

            # determine the index what has the first True value in the array of booleans
            # (the index of the timestep that corresponds to day 1 and hour 0 of the month)
            # np.nonzero() 함수는 배열에서 0이 아닌 원소의 인덱스를 반환하는 NumPy 함수
            # monthly_mask 배열에서 값이 True인 원소들의 인덱스를 반환합니다. 그리고 [0]은 이 튜플에서 첫 번째 요소를 선택함.
            # [0][0]은 이 첫 번째 요소 중에서도 첫 번째 값을 선택
            first_true = np.nonzero(monthly_mask)[0][0]

           # 택된 월에 해당하는 각 계산 기간 (PER)에 대한 수요 요금 계산을 추가하는 루프
            for per in pset:
                # Add demand charge calculation for each applicable billing period (PER) within the selected month

                # get an array that is True only for the selected month
                # 선택된 월의 각 시간 단계에 대해 billing_per_mask라는 새로운 배열을 생성(원본배열을 변경하지 않고)
                billing_per_mask = copy.deepcopy(monthly_mask)

                for i in range(first_true, first_true + len(month_sub_billing_period)):
                     # 선택된 월에 대한 원본 배열 값이 'True'인 경우에만 루프 실행
                    # loop through only the values that are 'True' (which should all be in order because
                    # the array should be sorted by datetime index) as they represent a month
                 
                    # I의 위치에 있는 값 재할당: PER이 해당하는지 여부에 따라
                    # (해당 계산 기간이 해당하지 않는 시간 단계의 'True' 값을 'False'로 재할당)
                    # reassign the value at I to be whether PER applies to the time corresponding to I
                    # (reassign each 'True' value to 'False' if the billing period does not apply to that timestep)
                    billing_per_mask[i] = per in sub_billing_period.iloc[i]

                # add a demand charge for each billing period in a month (for every month being optimized)
                # 열이 모두 'True'인 경우
                if np.all(billing_per_mask):
                    # billing_per_mask 배열이 모두 'True'인 경우, 전체 수요 요금에 해당 계산 기간의 수요 요금을 추가
                    total_demand_charges += self.tariff.loc[per, 'Value'] * annuity_scalar * cvx.max(net_load)
                else:
                    # billing_per_mask에 해당하는 시간 단계만 고려하여 수요 요금을 추가
                    total_demand_charges += self.tariff.loc[per, 'Value'] * annuity_scalar * cvx.max(net_load[billing_per_mask])
        TellUser.debug(f'time took to make demand charge term: {time.time() - start}')
        return {self.name: total_demand_charges}

    def timeseries_report(self):
        """ Summaries the optimization results for this Value Stream.
            이 Value Stream에 대한 최적화 결과를 요약
            
        Returns: A timeseries dataframe with user-friendly column headers that summarize the results
            pertaining to this instance

        """
        report = pd.DataFrame(index=self.billing_period.index)
        report.loc[:, 'Demand Charge Billing Periods'] = self.billing_period
        return report

    def drill_down_reports(self, monthly_data=None, time_series_data=None, technology_summary=None, **kwargs):
        """ Calculates any service related dataframe that is reported to the user.

        Returns: dictionary of DataFrames of any reports that are value stream specific
            keys are the file name that the df will be saved with

        """
        return {'demand_charges': self.tariff}
