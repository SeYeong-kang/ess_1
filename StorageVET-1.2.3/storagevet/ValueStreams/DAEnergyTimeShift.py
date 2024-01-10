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
DAEnergyTimeShift.py

This Python class contains methods and attributes specific for service analysis within StorageVet.
"""
from storagevet.ValueStreams.ValueStream import ValueStream
import cvxpy as cvx
import pandas as pd
import storagevet.Library as Lib
import numpy as np


# 전일 에너지 시간 이동 => 전력 그리드에서 발생하는 전력수요의 일부를 하루 전에 미리 예측 위해
class DAEnergyTimeShift(ValueStream):
    """ Day-Ahead Energy Time Shift. Each service will be daughters of the ValueStream class.

    """

    def __init__(self, params):
        """ Generates the objective function, finds and creates constraints.

        Args:
            params (Dict): input parameters
        """
        # ValueStream 클래스의 생성자 호출
        ValueStream.__init__(self, 'DA', params)

        # 'DA'라는 이름과 입력된 매개변수로 ValueStream 클래스 초기화
        self.price = params['price'] # 가격 정보
        self.growth = params['growth']/100  # growth rate of energy prices (%/yr) # 에너지 가격의 성장률 (%/yr)

    def grow_drop_data(self, years, frequency, load_growth):
        """ Adds data by growing the given data OR drops any extra data that might have slipped in.
        Update variable that hold timeseries data after adding growth data. These method should be called after
        add_growth_data and before the optimization is run.

        Args:
            years (List): list of years for which analysis will occur on
            frequency (str): period frequency of the timeseries data
            load_growth (float): percent/ decimal value of the growth rate of loads in this simulation


        """
        # 가격 정보에 성장 데이터 추가 및 추가된 데이터 제거
        self.price = Lib.fill_extra_data(self.price, years, self.growth, frequency)
        self.price = Lib.drop_extra_data(self.price, years)

    def objective_function(self, mask, load_sum, tot_variable_gen, generator_out_sum, net_ess_power, annuity_scalar=1):
        """ Generates the full objective function, including the optimization variables.

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
        # DA 가격 정보를 행렬 형태의 파라미터로 생성
        # CVXPY 라이브러리의 cvx.Parameter를 사용하여 DA 가격 정보를 행렬 형태의 파라미터로 생성하는 부분
        # DA 가격 정보를 나타내며, mask를 사용하여 해당하는 인덱스에 해당하는 값들로 초기화. 
        # 이 행렬의 형태는 shape=sum(mask)로 지정되어 해당 mask에 True가 있는 인덱스의 합만큼의 크기를 가지게 됨.
        p_da = cvx.Parameter(value=self.price.loc[mask].values, shape=sum(mask), name='DA_price')
        # 목적 함수의 핵심 부분 계산
        cost = cvx.sum(cvx.multiply(p_da, net_ess_power) + cvx.multiply(-p_da, generator_out_sum) + cvx.multiply(-p_da, tot_variable_gen) + cvx.multiply(p_da, load_sum))
        # 결과를 딕셔너리로 반환
        return {self.name: cost * annuity_scalar * self.dt}

    def timeseries_report(self):
        """ Summaries the optimization results for this Value Stream.

        Returns: A timeseries dataframe with user-friendly column headers that summarize the results
            pertaining to this instance

        """
        # 결과를 저장할 빈 데이터프레임 생성
        report = pd.DataFrame(index=self.price.index)

        # 데이터프레임에 'Energy Price ($/kWh)' 열 추가
        report.loc[:, 'Energy Price ($/kWh)'] = self.price

        # 최종 결과 데이터프레임 반환
        return report

    def drill_down_reports(self, monthly_data=None, time_series_data=None, technology_summary=None, **kwargs):
        """ Calculates any service related dataframe that is reported to the user.

        Returns: dictionary of DataFrames of any reports that are value stream specific
            keys are the file name that the df will be saved with

        """
        # 데이터프레임 딕셔너리 초기화
        df_dict = dict()
        # Energy Price 데이터프레임 생성
        # 'Energy Price ($/kWh)' 열을 선택하여 새로운 데이터프레임인 energy_price를 생성
        energy_price = time_series_data.loc[:, 'Energy Price ($/kWh)'].to_frame()
        # 데이터프레임에 'date' 열 추가 및 해당 열에 날짜 정보 할당
        energy_price.loc[:, 'date'] = time_series_data.index.date
        # 'hour' 열 추가 및 해당 열에 시간 정보 할당 (현재 시간에 1초를 더하고 시간 부분을 가져와 1을 더하여 'hour ending'을 표시)
        energy_price.loc[:, 'hour'] = (time_series_data.index + pd.Timedelta('1s')).hour + 1  # hour ending
        # 데이터프레임의 인덱스를 재설정하여 현재의 인덱스를 제거(drop=True)하고 새로운 정수 인덱스를 할당
        energy_price = energy_price.reset_index(drop=True)

        # energy_price 데이터프레임을 활용하여 pivot_table 함수를 이용해 새로운 데이터프레임 생성
        # values: 'Energy Price ($/kWh)' 열의 값을 사용
        # index: 'hour' 열을 인덱스로 사용
        # columns: 'date' 열을 열로 사용
        # 피벗 테이블은 'hour'와 'date'에 따른 'Energy Price ($/kWh)'의 맵을 나타냄.
        df_dict['energyp_map'] = energy_price.pivot_table(values='Energy Price ($/kWh)', index='hour', columns='date')

        # 최종 데이터프레임 딕셔너리 반환
        return df_dict

    def proforma_report(self, opt_years, apply_inflation_rate_func, fill_forward_func, results):
        """ Calculates the proforma that corresponds to participation in this value stream

        Args:
            opt_years (list): list of years the optimization problem ran for
            apply_inflation_rate_func:
            fill_forward_func:
            results (pd.DataFrame): DataFrame with all the optimization variable solutions

        Returns: A tuple of a DateFrame (of with each year in opt_year as the index and the corresponding
        value this stream provided), a list (of columns that remain zero), and a list (of columns that
        retain a constant value over the entire project horizon).
        """
        # 상위 클래스 메서드를 호출하여 프로포마 DataFrame을 가져옴.
        proforma = super().proforma_report(opt_years, apply_inflation_rate_func,
                                           fill_forward_func, results)
        
        # 각 연도에 대한 에너지 비용을 계산하고 프로포마 DataFrame에 추가합니다.
        #  DataFrame인 results에서 'Total Generation (kW)' 열을 선택
        energy_cost = self.dt * np.multiply(results['Total Generation (kW)'] + results['Total Storage Power (kW)'], self.price)
        for year in opt_years:
         # energy_cost DataFrame에서 연도가 주어진 year와 일치하는 부분을 선택하여 year_subset에 저장
            year_subset = energy_cost[energy_cost.index.year == year]
            proforma.loc[pd.Period(year=year, freq='y'), 'DA ETS'] = year_subset.sum()
         
        # 성장률과 함께 fill_forward_func을 프로포마 DataFrame에 적용합니다.
        # fill_forward_func: 누락된 값을 채우는 함수로, 이 함수는 이전의 값으로 결측값을 채우는 작업을 수행
        # 누락된 값이 성장률을 고려하여 채워지게 됨.
        proforma = fill_forward_func(proforma, self.growth)
        return proforma

    def update_price_signals(self, monthly_data, time_series_data):
        """ Updates attributes related to price signals with new price signals that are saved in
        the arguments of the method. Only updates the price signals that exist, and does not require all
        price signals needed for this service.

        Args:
            monthly_data (DataFrame): monthly data after pre-processing
            time_series_data (DataFrame): time series data after pre-processing

        """
        try:
            # 'DA Price ($/kWh)' 열을 time_series_data에서 찾아 self.price에 할당을 시도.
            self.price = time_series_data.loc[:, 'DA Price ($/kWh)']
        except KeyError:
            # 해당 열이 존재하지 않으면 KeyError 예외가 발생하며, 이 예외를 처리하여 아무 동작도 수행하지 않음.
            pass
