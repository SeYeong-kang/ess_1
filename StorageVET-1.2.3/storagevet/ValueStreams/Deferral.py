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
Deferral.py

This Python class contains methods and attributes specific for service analysis within StorageVet.
"""
import numpy as np
import cvxpy as cvx
from storagevet.ValueStreams.ValueStream import ValueStream
import pandas as pd
import storagevet.Library as Lib
import random
from storagevet.ErrorHandling import *
from storagevet.Library import truncate_float


class Deferral(ValueStream):
    """ Investment deferral. Each service will be daughters of the PreDispService class.

    """

    def __init__(self, params):
        """ Generates the objective function, finds and creates constraints.

          Args:
            params (Dict): input parameters
        """

        # generate the generic service object
        ValueStream.__init__(self, 'Deferral', params)

        # add Deferral specific attributes
        self.max_import = params['planned_load_limit']  # 계획 부하 한계값 (양수)
        self.max_export = params['reverse_power_flow_limit']  # 역전력 한계값 (음수)
        self.last_year = params['last_year'].year # 마지막 연도
        self.year_failed = params['last_year'].year + 1 # 실패로 간주되는 연도
        self.min_years = params.get('min_year_objective', 0) # 목적의 최소 연수
        self.load = params['load']  # deferral load 
        self.growth = params['growth']/100  # Deferral 부하의 성장률 (%/년)
        self.price = params['price']  # $/yr (연간비용)

        self.p_min = 0 # 최소 전력 ( 프로그램이 실행되면 필요한 값으로 업데이트 될 것이어 초기엔 0 으로 설정)
        self.e_min = 0 # 최소 에너지
        self.deferral_df = None # Deferral을 위한 데이터프레임
        self.e_walk = pd.Series() # 에너지 워크를 위한 시리즈 ( 초기에 빈 Series로 초기화되었으며, 이후 시뮬레이션 실행 중에 해당 Series에 데이터가 추가되거나 업데이트 됨)
        self.power_requirement = pd.Series() # 전력 요구 사항을 위한 시리즈

    def check_for_deferral_failure(self, end_year, poi, frequency, opt_years, def_load_growth):
        """This functions checks the constraints of the storage system against any predispatch or user inputted constraints
        for any infeasible constraints on the system.
        특정 시점에서 전력망 및 에너지 저장 시스템이 계획된 부하 한계를 초과하는지 확인하는 함수.
        The goal of this function is to predict the year that storage will fail to deferral a T&D asset upgrade.

        Only runs if Deferral is active.

        Args:
            end_year:
            poi:
            frequency:
            opt_years:
            def_load_growth:

        Returns: new list of optimziation years

        """
        # 첫 번째 재구축 실패 연도를 찾는 중임을 사용자에게 알림
        TellUser.info('Finding first year of deferral failure...')
        # 전력망 재구축 실패의 첫 해를 찾는다.
        current_year = self.load.index.year[-1]

        # 추가 연도 리스트 초기화
        additional_years = [current_year]
        try:
            # 크기 조절 최적화가 아닌 경우 실패 연도 찾기
            find_failure_year = not poi.is_sizing_optimization
        except AttributeError:
            # 예외 발생 시 기본적으로 실패 연도 찾기
            find_failure_year = True

        # get list of RTEs
        # RTE(Rated Technology Energy) 목록 가져오기
        rte_lst = [der.rte for der in poi.der_list if der.technology_type == 'Energy Storage System']
        
        # 각 DER(분산 에너지 자원) 유형별로 최대 충전/방전 및 에너지 용량 계산
        ess_cha_max = 0
        ess_dis_max = 0
        ess_ene_max = 0
        conventional_gen_max = 0
     
        for der_isnt in poi.der_list:
            if der_isnt.technology_type == "Energy Storage System":
             # 에너지 저장 시스템의 최대 충전/방전 및 에너지 용량 합산
                ess_dis_max += der_isnt.dis_max_rated #ess의 최대 방전 용량 누적
                # ene_max_rated는 ess의 최대 에너지 저장 용량
                # ulsoc는 ess의 최대 에너지 저장 용량에서 사용 가능한 실제 에너지 저장 용량의 비율
                # 최대 에너지 저장 용량을 누적한 값값
                ess_ene_max += der_isnt.ene_max_rated * der_isnt.ulsoc

            # DER(분산 에너지 자원)이 발전기(Generator)인 경우에 해당하는 블록을 실행
            if der_isnt.technology_type == 'Generator':
             # 발전기의 최대 방전 용량 합산
                conventional_gen_max += der_isnt.discharge_capacity()
             
        # Deferral에 관련된 결과를 저장할 열 초기화
        years_deferral_column = []
        min_power_deferral_column = []
        min_energy_deferral_column = []
     
        # 현재 연도가 종료 연도보다 작거나 같은 동안 반복
        while current_year <= end_year.year:
            size = len(self.load) #self.load 의 길이를 계산해 변수 size 에 할
            years_deferral_column.append(current_year)

            # TODO can we check the max year? or can we take the previous answer to calculate the next energy requirements?
            positive_feeder_load = self.load.values # Load에서 양적인 부하 데이터 가져오기
            negative_feeder_load = np.zeros(size) # 음적인 부하를 나타내는 배열 초기화

            # DER(분산 에너지 자원) 리스트를 반복하여 부하 및 DER의 에너지 요구 사항을 계산
            for der_isnt in poi.der_list:
                if der_isnt.technology_type == "Load":
                    positive_feeder_load = positive_feeder_load + der_isnt.value.values
                 # DER 유형이 "Intermittent Resource"이고 크기 조정이 진행 중이지 않은 경우
                if der_isnt.technology_type == "Intermittent Resource" and not der_isnt.being_sized():
                    # TODO: should take PV variability into account here (PV 변동성 고려)
                    negative_feeder_load = negative_feeder_load - der_isnt.maximum_generation()

         
            # 발전소에서 발생하는 전력을 더함.
            positive_feeder_load += np.repeat(conventional_gen_max, size)

         
            # Determine power requirement of the storage:
            # (1) anytime the net_feeder_load goes above deferral_max_import (too much load) (초과의 경우)
            positive_0load_power_req = positive_feeder_load - self.max_import
            # clip() 함수는 배열이나 시리즈에서 값을 자를 때 사용함.
            # 여기서 min=0은 값을 0 미만으로 가지지 않도록 하는 것 의미. 즉 양수값만 유지 
            positive_power_req = positive_load_power_req.clip(min=0)
            # (2) anytime the net_feeder_load goes below deferral_max_exports
            # (assumes deferral_max_export < 0)  (too much generation)
            negative_load_power_req = negative_feeder_load - self.max_export
            negative_power_req = negative_load_power_req.clip(max=0) #모든 양수 값을 0으로 만들어줌.
            # The sum of (1) and (2)
            storage_power_requirement = positive_power_req + negative_power_req
         
            # 여기서 코드는 먼저 precheck_failure 메서드를 호출하여 에너지 저장 시스템의 실패 여부를 사전에 확인
            e_walk, _ = self.precheck_failure(self.dt, rte_lst, storage_power_requirement)

            # 로그에 현재 연도와 최소 전력 및 에너지 요구 사항을 기록
            TellUser.debug(f'In {current_year} -- min power: {truncate_float(self.p_min)}  min energy: {truncate_float(self.e_min)}')
         
            # save min power and energy requirements
            min_power_deferral_column.append(self.p_min)
            min_energy_deferral_column.append(self.e_min)
            # save energy required as function of time & storage power required as function of time
            # 에너지 요구를 시간에 따른 함수로 저장하고 저장소 전력 요구를 시간에 따른 함수로 저장
            self.e_walk = pd.Series(e_walk, index=self.load.index)
            self.power_requirement = pd.Series(storage_power_requirement, index=self.load.index)

            # 실패 연도를 찾아낼 필요가 있고, 최소 전력 또는 최소 에너지 요구 사항이 ess의 능력을 초과하는 경우
            if find_failure_year and (self.p_min > ess_dis_max or self.p_min > ess_cha_max or self.e_min > ess_ene_max):
                # then we predict that deferral will fail
                last_deferral_yr = current_year - 1
                # 마지막으로 실패 연도를 설정
                self.set_last_deferral_year(last_deferral_yr, current_year)
             
                # 최적화 연도 목록을 업데이트
                opt_years = list(set(opt_years + additional_years))
                # 실패 연도 찾기를 종료.
                find_failure_year = False
                # 정보 메시지를 출력하여 분석 연도가 업데이트되었음을 알림.
                TellUser.info(f'{self.name} updating analysis years: {opt_years}')

            # the current year we have could be the last year the deferral is possible, so we want
            # to keep it in self.opt_results until we know the next is can be deferred as well
            additional_years = [current_year, current_year + 1]
            next_opt_years = list(set(opt_years + additional_years))

            # add additional year of data to der data
            for der in poi.der_list:
                der.grow_drop_data(next_opt_years, frequency, def_load_growth)

            # add additional year of data to deferred load
            self.grow_drop_data(next_opt_years, frequency, def_load_growth)

            # index the current year by one
            current_year += 1

       # 최종 연도, 최소/최대 충전 및 방전 및 에너지 요구 조건을 포함하는 데이터프레임 생성
        self.deferral_df = pd.DataFrame({'Year': years_deferral_column,
                                         'Power Capacity Requirement (kW)': min_power_deferral_column,
                                         'Energy Capacity Requirement (kWh)': min_energy_deferral_column})
        # inplace=True를 사용하면 반환값이 없고, 기존 객체가 변경
        # DataFrame의 특정 열(Year)을 새로운 인덱스로 설정
        self.deferral_df.set_index('Year', inplace=True)
        
         # 최적 연도 목록 반환
        return opt_years

    def precheck_failure(self, tstep, rte_lst, sto_p_req):
        """
        This function takes in a vector of storage power requirements (negative=charging and positive=discharging) [=] kW
        that are required to perform the deferral as well as a time step (tstep) [=] hrs

        Args:
            tstep (float): timestep of the data in hours
            rte_lst (list): round trip efficiency of storage
            sto_p_req (list, ndarray): storage power requirement

        Returns:
            how much the energy in the ESS needs to wander as a function of time,
            theoretical dispatch of the ESS to meet on feeder limits

        Notes:
            This algorithm can reliably find the last year deferral is possible, however the problem might still
            be found INFEASIBLE if the ESS cannot use it's full range of SOC (ie. if LLSOC is too high or ULSOC is too low)
        """
        # Loop through time steps. If the storage is forced to dispatch from the constraint,
        # return to nominal SOC as soon as possible after.
        self.p_min = max(abs(sto_p_req))
        # TODO: determine min energy requirement in static recursive function to speed runtime --HN

        # np.zeros는 주어진 크기의 모든 원소가 0으로 초기화된 NumPy 배열을 생성하는 함수
        # to_p_req.shape는 sto_p_req 배열의 모양(shape)을 나타내며, 이를 기반으로 크기가 같은 원소가 0으로 초기화된 배열이 생성
        sto_dispatch = np.zeros(sto_p_req.shape)
        e_walk = np.zeros(sto_p_req.shape)  # how much the energy in the ESS needs to wander #Definitely not a star wars pun
        # len(sto_p_req)는 sto_p_req 배열 또는 리스트의 길이를 반환
        # range(len(sto_p_req))는 0부터 len(sto_p_req) - 1까지의 숫자를 생성하는 반복 가능한 객체
        for step in range(len(sto_p_req)):
            if step == 0:
                e_walk[step] = -tstep * sto_p_req[0]  # initialize at nominal SOC
                sto_dispatch[step] = sto_p_req[0]  # ignore constaints imposed by the first timestep of the year
            elif sto_p_req[step] > 0:  # if it is required to dispatch, do it
                #  배열 sto_p_req의 step 인덱스 위치에 있는 값을 배열 sto_dispatch의 step 인덱스 위치에 할당
                sto_dispatch[step] = sto_p_req[step]
                e_walk[step] = e_walk[step - 1] - sto_dispatch[step] * tstep  # kWh
            elif sto_p_req[step] < 0:
                sto_dispatch[step] = sto_p_req[step]
                random_rte = random.choice(rte_lst)
                e_walk[step] = e_walk[step - 1] - sto_dispatch[step] * tstep * random_rte
            elif e_walk[step - 1] < 0:  # Otherwise contribute its full power to returning energy to nominal
                sto_dispatch[step] = -min(abs(self.p_min), abs(e_walk[step - 1] / tstep), abs(self.max_import - self.load.iloc[step]))
                # random.choice() 함수는 주어진 시퀀스(리스트, 튜플 등)에서 무작위로 하나의 요소를 선택하는 함수
                random_rte = random.choice(rte_lst)
                e_walk[step] = e_walk[step - 1] - sto_dispatch[step] * tstep * random_rte  # kWh
            elif e_walk[step - 1] > 0:
                sto_dispatch[step] = min(abs(self.p_min), abs(e_walk[step - 1] / tstep))
                e_walk[step] = e_walk[step - 1] - sto_dispatch[step] * tstep  # kWh
            else:
                sto_dispatch[step] = 0
                e_walk[step] = e_walk[step - 1]
        kWh_min = max(e_walk) - min(e_walk)
        self.e_min = float(kWh_min)
        return e_walk, sto_dispatch

    def grow_drop_data(self, years, frequency, load_growth):
        """ Adds data by growing the given data OR drops any extra data that might have slipped in.
        Update variable that hold timeseries data after adding growth data. These method should be called after
        add_growth_data and before the optimization is run.
        성장 데이터를 추가한 후 최적화를 실행하기 전에 이러한 메서드를 호출해야 함. 

        Args:
            years (List): list of years for which analysis will occur on
            frequency (str): period frequency of the timeseries data
            load_growth (float): percent/ decimal value of the growth rate of loads in this simulation

        """
        # 데이터 성장 및 불필요한 데이터 삭제
        self.load = Lib.fill_extra_data(self.load, years, self.growth, frequency)
        self.load = Lib.drop_extra_data(self.load, years)

    def set_last_deferral_year(self, last_year, failed_year):
        """Sets last year that deferral is possible
        저장장치의 T&D(Technology & Development) 장비 업그레이드를 연기할 수 있는 마지막 해를 설정합니다

        Args:
            last_year (int): The last year storage can defer an T&D equipment upgrade
            failed_year (int): the year that deferring an upgrade will fail
        """
        self.last_year = last_year
        self.year_failed = failed_year
        # str() : 변수를 문자열로 반환 >> Telluser.info 함수가 문자열을 받아서 출력하기 때문
        TellUser.info(f'{self.name} year failed set to: ' + str(self.year_failed))

    def constraints(self, mask, load_sum, tot_variable_gen, generator_out_sum, net_ess_power, combined_rating):
        """Default build constraint list method. Used by services that do not have constraints.
          기본 제약조건 목록을 생성하는 메서드입니다. 제약조건이 없는 서비스에서 사용됨.

        Args:
            mask (DataFrame): A boolean array that is true for indices corresponding to time_series data included
                    in the subs data set
            tot_variable_gen (Expression): the sum of the variable/intermittent generation sources
            load_sum (list, Expression): the sum of load within the system
            generator_out_sum (list, Expression): the sum of conventional generation within the system
            net_ess_power (list, Expression): the sum of the net power of all the ESS in the system. [= charge - discharge]
            combined_rating (Dictionary): the combined rating of each DER class type

        Returns:
            An empty list (for aggregation of later constraints)
        """
        # adding constraints to ensure power dispatch does not violate thermal limits of transformer deferred
        # only include them if deferral is not going to fail
        constraints = []
        # loc[mask]는 이 불리언 배열을 사용하여 데이터프레임을 필터링하고, 그 결과에서 인덱스를 선택
        # .index.year는 선택된 인덱스의 연도 부분만 추출
        # [-1]은 그 중에서 마지막 연도를 선택
        year_of_optimization = mask.loc[mask].index.year[-1]
        if year_of_optimization < self.year_failed:
            # shape: sum(mask)는 mask 배열에서 참인 요소의 수를 나타내며, 이는 파라미터의 형태를 정의
            load_beyond_poi = cvx.Parameter(value=self.load.loc[mask].values, name='deferral_load', shape=sum(mask))
            # -(max export) >= dis - ch + generation - loads
            constraints += [cvx.NonPos(self.max_export - load_sum - load_beyond_poi + (-1)*net_ess_power + generator_out_sum + tot_variable_gen)]
            # max import >= loads - (dis - ch) - generation
            # cvx.NonPos: 이 함수는 주어진 표현식이 Non-Positive임을 나타내는 CVXPY의 함수
            constraints += [cvx.NonPos(load_sum + load_beyond_poi + net_ess_power + (-1)*generator_out_sum + (-1)*tot_variable_gen - self.max_import)]
            # TODO make sure power does doesn't violate the constraints during dispatch service activity
        else:
            TellUser.debug(f"{self.name} did not add any constraints to our system of equations")

        return constraints

    def timeseries_report(self):
        """ Summaries the optimization results for this Value Stream.

        Returns: A timeseries dataframe with user-friendly column headers that summarize the results
            pertaining to this instance

        """
        # 결과를 저장할 데이터프레임 생성
        report = pd.DataFrame(index=self.load.index)
        # 'Deferral: Load (kW)' 열에 부하 데이터 추가
        report.loc[:, 'Deferral: Load (kW)'] = self.load
        # 'Deferral: Energy Requirement (kWh)' 열에 에너지 요구량 데이터 추가 (음수는 방전을 나타냄)
        report.loc[:, 'Deferral: Energy Requirement (kWh)'] = -self.e_walk
        # 'Deferral: Power Requirement (kW)' 열에 전력 요구량 데이터 추가
        report.loc[:, 'Deferral: Power Requirement (kW)'] = self.power_requirement
         # 결과를 시간순으로 정렬하여 반환
        return report.sort_index()

    def update_yearly_value(self, new_value: float):
        """ Updates the attribute associated to the yearly value of this service. (used by CBA)
            서비스의 연간 가치에 연결된 속성을 업데이트

        Args:
            new_value (float): the dollar yearly value to be assigned for providing this service

        """
        self.price = new_value

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
        # 결과에서 연도 정보 추퉁
        years = results.index.year.unique()
        start_year = min(years)
        end_year = max(years)
        # 연도별 인덱스 생성 
        yr_index = pd.period_range(start=start_year, end=end_year, freq='y')
     
        # 프로포마를 담을 DataFrame 초기화
        # np.zeros는 주어진 크기의 모든 원소가 0으로 초기화된 NumPy 배열을 생성하는 함수
        proforma = pd.DataFrame(data={self.name + ' Value': np.zeros(len(yr_index))}, index=yr_index)

        for year in yr_index:

            if year.year < self.year_failed:
                # 연도가 실패 연도보다 작을 경우에만 가치를 할당
                # .loc 특정 열이나 행 선택
                proforma.loc[year, self.name + ' Value'] = self.price
        # apply inflation rates
        proforma = apply_inflation_rate_func(proforma, None, min(opt_years))

        return proforma

    def drill_down_reports(self, monthly_data=None, time_series_data=None, technology_summary=None, **kwargs):
        """ Calculates any service related dataframe that is reported to the user.
            사용자에게 보고된 모든 서비스 관련 DataFrame을 계산합니다.
        Returns: dictionary of DataFrames of any reports that are value stream specific
            keys are the file name that the df will be saved with

        """
        return {'deferral_results': self.deferral_df}
