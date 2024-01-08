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
EnergyTimeShift.py

This Python class contains methods and attributes specific for service analysis within StorageVet.
"""
from storagevet.ValueStreams.ValueStream import ValueStream
import numpy as np
import cvxpy as cvx
import pandas as pd
from storagevet.Finances import Financial
import storagevet.Library as Lib
from storagevet.ErrorHandling import *


SATURDAY = 5


class EnergyTimeShift(ValueStream):
    """ Retail energy time shift. A behind the meter service.

    """

    def __init__(self, params):
        """ Generates the objective function, finds and creates constraints.

        Args:
            params (Dict): input parameters
        """
        ValueStream.__init__(self, 'retailETS', params)
        self.price = params['price']
        self.tariff = params['tariff']
        self.growth = params['growth']/100

        self.billing_period_bill = pd.DataFrame() # 빈 데이터프레임 생성
        self.monthly_bill = pd.DataFrame()

    def grow_drop_data(self, years, frequency, load_growth):
        """ Adds data by growing the given data OR drops any extra data that might have slipped in.
        Update variable that hold timeseries data after adding growth data. These method should be called after
        add_growth_data and before the optimization is run.

        Args:
            years (List): list of years for which analysis will occur on
            frequency (str): period frequency of the timeseries data
            load_growth (float): percent/ decimal value of the growth rate of loads in this simulation


        """
        data_year = self.price.index.year.unique() # 현재 객체의 가격 데이터에서 연도를 추출
        no_data_year = {pd.Period(year) for year in years} - {pd.Period(year) for year in data_year}  # which years do we not have data for

        if len(no_data_year) > 0: # 불필요한 데이터가 있는 경우, 해당 연도에 대한 처리를 진행
            for yr in no_data_year:
                source_year = pd.Period(max(data_year))

                years = yr.year - source_year.year

                # Build Energy Price Vector based on the new year(새로운 연도를 기반으로 에너지 가격 벡터 작성)
                new_index = Lib.create_timeseries_index([yr.year], frequency)
                temp = pd.DataFrame(index=new_index)

                # new_index의 각 날짜에 대해 토요일 이전인지 여부를 판단하여 해당 날짜가 토요일 이전이면 1, 이후이면 0으로 설정.
                weekday = (new_index.weekday < SATURDAY).astype('int64')
                # new_index에 1초를 더한 후 해당 날짜의 시간을 추출하고, 1을 더하여 해당 시간대를 구함.
                he = (new_index + pd.Timedelta('1s')).hour + 1
                #  새로운 인덱스 길이만큼 0으로 초기화
                temp['price'] = np.zeros(len(new_index))

                for p in range(len(self.tariff)):
                    # edit the pricedf energy price and period values for all of the periods defined
                    # in the tariff input file
                    # iloc을 사용하여 정수 위치를 기반으로 행을 선택
                    bill = self.tariff.iloc[p, :]
                    mask = Financial.create_bill_period_mask(bill, temp.index.month, he, weekday)
                 
                    # 조건에 맞는 인덱스를 가진 temp 데이터프레임에서 'price' 열의 값을 추출하여 배열로 반환
                    current_energy_prices = temp.loc[mask, 'price'].values
                    # current_energy_prices 배열 중에서 0보다 큰 값이 하나라도 있는지 확인하는 부분
                    # np.any()는 해당 배열 중 하나 이상의 요소가 True인지 검사
                    if np.any(np.greater(current_energy_prices, 0)):
                        # More than one energy price applies to the same time step
                        TellUser.warning('More than one energy price applies to the same time step.')
                    # Add energy prices
                    # 현재 에너지 가격이 적용되는 시간대에 대해 bill['Value']만큼의 값을 기존 에너지 가격에 더해주는 작업을 수행
                    temp.loc[mask, 'price'] += bill['Value']
                # apply growth to new energy rate
                # ** : 거듭제곱
                new_p_energy = temp['price']*(1+self.growth)**years
                #  self.price와 new_p_energy 두 개의 데이터프레임을 이어붙이는(concatenating) 작업을 수행
                self.price = pd.concat([self.price, new_p_energy], sort=True)  # add to existing

    def objective_function(self, mask, load_sum, tot_variable_gen, generator_out_sum, net_ess_power, annuity_scalar=1):
        """ Generates the full objective function, including the optimization variables.
        최적화 문제를 위한 목적 함수를 생성

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
            A dictionary with expression of the objective function that it affects. This can be passed into the cvxpy solver.

        """
        # 'mask'에 포함된 시계열 데이터의 수를 계산하여 'size'에 할당
        size = sum(mask)
        # 'energy_price' 파라미터를 생성하고, 'mask'에 해당하는 에너지 가격 데이터를 값으로 설정
        price = cvx.Parameter(size, value=self.price.loc[mask].values, name='energy_price')

        # cvx.multiply(a, b)는 a와 b의 각 원소를 곱한 결과를 반환
        load_price = cvx.multiply(price, load_sum)
        ess_net_price = cvx.multiply(price, net_ess_power)
        variable_gen_prof = cvx.multiply(-price, tot_variable_gen)
        generator_prof = cvx.multiply(-price, generator_out_sum)

        cost = cvx.sum(load_price + ess_net_price + variable_gen_prof + generator_prof)
        return {self.name: cost * self.dt * annuity_scalar}

    def timeseries_report(self):
        """ Summaries the optimization results for this Value Stream.

        Returns: A timeseries dataframe with user-friendly column headers that summarize the results
            pertaining to this instance

        """
         # 빈 데이터프레임을 생성하고 인덱스를 energy price의 인덱스로 설정
        report = pd.DataFrame(index=self.price.index)
        # 'Energy Price ($/kWh)' 열을 생성하고 해당 열의 값으로 energy price를 설정
        report.loc[:, 'Energy Price ($/kWh)'] = self.price
        return report

    def drill_down_reports(self, monthly_data=None, time_series_data=None, technology_summary=None, **kwargs):
        """ Calculates any service related dataframe that is reported to the user.
        사용자에게 보고될 다양한 서비스 관련 데이터프레임을 계산

        Returns: dictionary of DataFrames of any reports that are value stream specific
            keys are the file name that the df will be saved with

        """
        # 결과를 저장할 딕셔너리 생성
        df_dict = dict()

        # 시계열 데이터로부터 에너지 가격 데이터 추출
        # time_series_data 데이터프레임에서 'Energy Price ($/kWh)' 열만 추출
        # .to_frame(): 선택한 열을 데이터프레임 형태로 변환
        energy_price = time_series_data.loc[:, 'Energy Price ($/kWh)'].to_frame()

        # 'date' 및 'hour' 열 추가
        # energy_price.loc[:, 'date']: energy_price 데이터프레임에서 모든 행의 'date' 열을 선택
        # time_series_data.index.date: time_series_data 데이터프레임의 인덱스를 날짜 형식으로 변환
        energy_price.loc[:, 'date'] = time_series_data.index.date 
        # energy_price.loc[:, 'hour']: energy_price 데이터프레임에서 모든 행의 'hour' 열을 선택
        # 데이터프레임의 인덱스에 1초를 더한 새로운 시간을 계산
        # .hour: 새로 조정된 시간에서 시간 정보만을 추출
        # + 1: 시간 정보에 1을 더하여 1부터 24까지의 시간을 나타내도록 조정
        energy_price.loc[:, 'hour'] = (time_series_data.index + pd.Timedelta('1s')).hour + 1  # hour ending

        # 인덱스 리셋 및 결과 데이터프레임 준비
        # drop=True는 이전 인덱스를 열로 유지하지 않고, 새로운 정수 인덱스를 할당하도록 지시
        energy_price = energy_price.reset_index(drop=True)

        # 'energyp_map' 키에 해당하는 데이터프레임을 딕셔너리에 추가
        # df_dict['energyp_map']: 딕셔너리 df_dict에 'energyp_map'이라는 키를 추가
        # energy_price 데이터프레임을 pivot table로 변환합니다. 'Energy Price ($/kWh)' 열의 값이 테이블의 값으로, 'hour'를 행 인덱스로, 'date'를 열 인덱스로 사용
        # 데이터프레임은 'hour'와 'date'를 기준으로 에너지 가격을 표시한 pivot table.
        df_dict['energyp_map'] = energy_price.pivot_table(values='Energy Price ($/kWh)', index='hour', columns='date')
        return df_dict
