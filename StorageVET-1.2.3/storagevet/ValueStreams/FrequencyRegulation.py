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
FrequencyRegulation.py

This Python class contains methods and attributes specific for service analysis
 within StorageVet.
"""
from storagevet.ValueStreams.MarketServiceUpAndDown import MarketServiceUpAndDown
import cvxpy as cvx
import numpy as np
import storagevet.Library as Lib


class FrequencyRegulation(MarketServiceUpAndDown):
    """ Frequency Regulation. Each service will be daughters of the ValueStream
    class.

    """

    def __init__(self, params):
        """ Generates the objective function, finds and creates constraints.
        Args:
            params (Dict): input parameters
        """
        # financials_df = financials.fin_inputs
        # # MarketServiceUpAndDown 클래스의 생성자 호출하여 초기화
        MarketServiceUpAndDown.__init__(self, 'FR', 'Frequency Regulation', params)

        # 전체 클래스에 사용될 변수 초기화
        # get 메서드는 딕셔너리에서 주어진 키에 대한 값을 반환. 만약 해당 키가 존재하지 않으면 False를 반환
        self.u_ts_constraints = params.get('u_ts_constraints', False)
        self.d_ts_constraints = params.get('d_ts_constraints', False)

        # 상승 및 하강 제약 조건이 주어진 경우, 해당 변수 초기화
        if self.u_ts_constraints:
            # 딕셔너리에서 'regu_max' 키에 대한 값을 가져옴옴
            self.regu_max = params['regu_max']
            self.regu_min = params['regu_min']
        if self.d_ts_constraints:
            self.regd_max = params['regd_max']
            self.regd_min = params['regd_min']

    def grow_drop_data(self, years, frequency, load_growth):
        """ Adds data by growing the given data OR drops any extra data that
        might have slipped in. Update variable that hold timeseries data
        after adding growth data. These method should be called after
        add_growth_data and before the optimization is run.

        Args:
            years (List): list of years for which analysis will occur on
            frequency (str): period frequency of the timeseries data
            load_growth (float): percent/ decimal value of the growth rate of
                loads in this simulation

        """
        # 부모 클래스의 메서드 호출
        # 반환된 super 객체를 이용하여 부모 클래스의 grow_drop_data 메서드를 호출
        # 이때, years, frequency, load_growth는 인자로 전달
        super().grow_drop_data(years, frequency, load_growth)

        # 상승 제약 조건이 주어진 경우, regu_max 및 regu_min 데이터 처리
        if self.u_ts_constraints:
            # Lib 모듈(또는 클래스)에 정의된 fill_extra_data 함수를 호출
            # self.regu_max 데이터에 대해 주어진 연도(years), 초기값(0), 그리고 주기(frequency)를 사용하여 데이터를 채우는 역할
            self.regu_max = Lib.fill_extra_data(self.regu_max, years, 0,
                                                frequency)
            # self.regu_max 데이터에서 주어진 연도(years)에 해당하지 않는 데이터를 삭제하는 역할
            self.regu_max = Lib.drop_extra_data(self.regu_max, years)

            self.regu_min = Lib.fill_extra_data(self.regu_min, years, 0,
                                                frequency)
            self.regu_min = Lib.drop_extra_data(self.regu_min, years)

        # 하강 제약 조건이 주어진 경우, regd_max 및 regd_min 데이터 처리
        if self.d_ts_constraints:
            self.regd_max = Lib.fill_extra_data(self.regd_max, years, 0,
                                                frequency)
            self.regd_max = Lib.drop_extra_data(self.regd_max, years)

            self.regd_min = Lib.fill_extra_data(self.regd_min, years, 0,
                                                frequency)
            self.regd_min = Lib.drop_extra_data(self.regd_min, years)

    def constraints(self, mask, load_sum, tot_variable_gen, generator_out_sum,
                    net_ess_power, combined_rating):
        """build constraint list method for the optimization engine
           최적화 엔진을 위해 제약 조건 목록을 생성하는 메서드

        Args:
            mask (DataFrame): A boolean array that is true for indices
                corresponding to time_series data included in the subs data set
            tot_variable_gen (Expression): the sum of the variable/intermittent
                generation sources
            load_sum (list, Expression): the sum of load within the system
            generator_out_sum (list, Expression): the sum of conventional
                generation within the system
            net_ess_power (list, Expression): the sum of the net power of all
                the ESS in the system. flow out into the grid is negative
            combined_rating (Dictionary): the combined rating of each DER class
                type

        Returns:
            An list of constraints for the optimization variables added to
            the system of equations
        """

        # 부모 클래스의 constraints 메서드 호출하여 초기화 작업을 수행
        #  부모 클래스인 MarketServiceUpAndDown 클래스의 constraints 메서드를 호출하고, 그 결과를 constraint_list 변수에 할당
        constraint_list = super().constraints(mask, load_sum, tot_variable_gen,
                                              generator_out_sum,
                                              net_ess_power, combined_rating)
        # add time series service participation constraints, if called for
        #   Reg Up Max and Reg Up Min will constrain the sum of up_ch + up_dis
        if self.u_ts_constraints:
            # 상승 제약 조건에 대한 항목을 추가
            # cvx.NonPos를 사용하여 표현식이 non-positive
            constraint_list += [
                cvx.NonPos(self.variables['up_ch'] + self.variables['up_dis']
                           - self.regu_max.loc[mask])
            ]
           # 또 다른 상승 제약 조건을 constraint_list에 추가하는 역할
            constraint_list += [
                cvx.NonPos((-1)*self.variables['up_ch'] + (-1)*self.variables[
                    'up_dis'] + self.regu_min.loc[mask])
            ]
        #   Reg Down Max and Reg Down Min will constrain the sum down_ch+down_dis
        if self.d_ts_constraints:
            constraint_list += [
                cvx.NonPos(self.variables['down_ch'] + self.variables['down_dis']
                           - self.regd_max.loc[mask])
            ]
            constraint_list += [
                cvx.NonPos(-self.variables['down_ch'] - self.variables['down_dis']
                           + self.regd_min.loc[mask])
            ]

        return constraint_list

    def timeseries_report(self):
        """ Summaries the optimization results for this Value Stream.

        Returns: A timeseries dataframe with user-friendly column headers that
            summarize the results pertaining to this instance

        """
       # 부모 클래스인 MarketServiceUpAndDown의 timeseries_report 메서드 호출
        report = super(FrequencyRegulation, self).timeseries_report()\

       # 상향 제어 시간대 제약이 있는 경우 해당 열을 추가
        if self.u_ts_constraints:
            # 열(column)을 지정하여 해당 열에 대한 값을 설정
            # loc 메서드를 사용하여 report DataFrame에 self.regu_max의 값을 채우는 역할
            report.loc[:, self.regu_max.name] = self.regu_max
            report.loc[:, self.regu_min.name] = self.regu_min

        # 하향 제어 시간대 제약이 있는 경우 해당 열을 추가
        if self.d_ts_constraints:
            report.loc[:, self.regd_max.name] = self.regd_max
            report.loc[:, self.regd_min.name] = self.regd_min

        return report

    def update_price_signals(self, monthly_data, time_series_data):
        """ Updates attributes related to price signals with new price signals
            새로운 가격 신호로 관련된 속성을 업데이트
        that are saved in the arguments of the method. Only updates the
        price signals that exist, and does not require all price signals
        needed for this service.

        Args:
            monthly_data (DataFrame): monthly data after pre-processing
            time_series_data (DataFrame): time series data after pre-processing

        """
        if self.combined_market:
            # "FR Price ($/kW)" 열이 time_series_data DataFrame에 존재하지 않을 경우 KeyError 예외가 발생
            # try 블록 안에서 해당 열을 가져오려 시도.
            # 만약 해당 열이 없다면(KeyError 예외가 발생하면) except 블록으로 이동하여 아무 동작도 수행하지 않
            try:
                # loc은 행과 열을 선택하기 위한 메서드이며, [:, 'FR Price ($/kW)']는 모든 행을 선택하고 'FR Price ($/kW)' 열을 선택
                #  'FR Price ($/kW)' 열의 모든 행을 가져와 변수 fr_price에 할당
                fr_price = time_series_data.loc[:, 'FR Price ($/kW)']
            except KeyError:
                pass
            else:
                # NumPy의 np.divide 함수를 사용하여 fr_price의 모든 값을 2로 나눔.
                self.p_regu = np.divide(fr_price, 2)
                self.p_regd = np.divide(fr_price, 2)

            try:
                self.price = time_series_data.loc[:, 'DA Price ($/kWh)']
            except KeyError:
                pass
        else:
            try:
                self.p_regu = time_series_data.loc[:, 'Reg Up Price ($/kW)']
            except KeyError:
                pass

            try:
                self.p_regd = time_series_data.loc[:, 'Reg Down Price ($/kW)']
            except KeyError:
                pass

            try:
                self.price = time_series_data.loc[:, 'DA Price ($/kWh)']
            except KeyError:
                pass

    def min_regulation_up(self):
        if self.u_ts_constraints:
            return self.regu_min
            # 부모 클래스의 (super().min_regulation_up()) 메서드를 호출하여 그 결과를 반환
        return super().min_regulation_up()

    def min_regulation_down(self):
        if self.d_ts_constraints:
            return self.regd_min
        return super().min_regulation_down()

    def max_participation_is_defined(self):
        # self 객체에 'regu_max' 또는 'regd_max' 속성 중 하나라도 존재하는 경우에 True를 반환하고, 그렇지 않으면 False를 반환
        # hasattr 함수는 객체가 특정 속성을 가지고 있는지 확인하는 데 사용됨.
        return hasattr(self, 'regu_max') or hasattr(self, 'regd_max')
