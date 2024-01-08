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
DemandResponse.py

This Python class contains methods and attributes specific for service analysis within StorageVet.
"""
from storagevet.ValueStreams.ValueStream import ValueStream
import pandas as pd
import cvxpy as cvx
import numpy as np
from storagevet.ErrorHandling import *
from storagevet.SystemRequirement import Requirement
import storagevet.Library as Lib

SATURDAY = 5


class DemandResponse(ValueStream):
    """ Demand response program participation. Each service will be daughters of the ValueStream class.
        수요 반응 프로그램 참여
    """

    def __init__(self, params):
        """ Generates the objective function, finds and creates constraints.
            목적 함수를 생성하고 제약 조건을 찾고 생성

          Args:
            params (Dict): input parameters

        """

        # generate the generic service object
        ValueStream.__init__(self, 'Demand Response', params)

        # add dr specific attributes to object
        self.days = params['days']
        self.length = params.get('length')  # length of an event
        self.weekend = params['weekend'] # 주말 이벤트 여부
        self.start_hour = params['program_start_hour'] # 프로그램 시작 시간
        self.end_hour = params.get('program_end_hour')  # 프로그램 종료 시간
        self.day_ahead = params['day_ahead']  # 이벤트가 실시간으로 예약되었는지 또는 하루 전에 예약되었는지 여부
        self.growth = params['growth'] / 100  # DR 가격의 성장률 (%에서 십진수로 변환)

        # handle length and end_hour attributes here
        self.fill_dr_event_details()

        # timeseries data
        self.system_load = params['system_load']  # 전체 시스템 부하
        # params['dr_months']가 1이면 self.months는 True가 되고, 그렇지 않으면 False가 됩니다. 
        # 이렇게 1을 선택하는 이유는 아마도 DR 프로그램이 참여 가능한 월을 나타내기 위함(...?)
        self.months = params['dr_months'] == 1
        self.cap_commitment = params['dr_cap']  # 수용 가능한 총 용량

        # monthly data 
        self.cap_monthly = params['cap_monthly']  # 월별 참여 가능 최대 전력 (kW)
        self.cap_price = params['cap_price'] # 전력 용량 가격 ($/kW)
        self.ene_price = params['ene_price'] # 에너지 가격 ($/kWh)

        # the following attributes will be used to save values during analysis
        self.qc = None # 품질 제어(QC) 변수 초기화
        self.qe = None  # 에너지 효율(QE) 변수 초기화
        self.der_dispatch_discharge_min_constraint = pd.Series()  # DER 방전 최소 제약조건 초기화
        self.possible_event_times = None # 가능한 이벤트 시간 초기화

    def fill_dr_event_details(self):
        """ Ensure consistency in length and end_hour attributes
            This will set the length attribute accordingly if it's None initially
            This will set the end_hour attribute accordingly if it's None initially
            Will raise an error if both values are not consistent
            Note: if both are None an error is raised first in Params class

    길이와 end_hour 속성의 일관성을 확인합니다.
    이 함수는 length 속성이 초기에 None이면 적절한 값으로 설정합니다.
    end_hour 속성이 초기에 None이면 적절한 값으로 설정합니다.
    두 값이 일관되지 않으면 오류를 발생시킵니다.
    참고: 두 값이 모두 None이면 먼저 Params 클래스에서 오류가 발생합니다.
        """
        if isinstance(self.length, str): # 이벤트 길이(self.length) 값이 문자열인 경우 오류를 발생시킵니다.
            TellUser.error(f'Demand Response: the value of event length ({self.length}) is not supported')
            raise ModelParameterError(f'Demand Response: the event value of length ({self.length}) is not supported')
        if isinstance(self.end_hour, str): # 프로그램 종료 시간(self.end_hour) 값이 문자열인 경우 오류를 발생시킵니다.
            TellUser.error(f'Demand Response: the value of program_end_hour ({self.end_hour}) is not supported')
            raise ModelParameterError(f'Demand Response: the value of program_end_hour ({self.end_hour}) is not supported')
        if self.length is None:
            self.length = self.end_hour - self.start_hour + 1
        elif self.end_hour is None:
            self.end_hour = self.start_hour + self.length - 1

        # require that LENGTH < END_HOUR - START_HOUR
        # 이벤트 길이(self.length)가 프로그램 종료 시간과 프로그램 시작 시간의 차이와 일치하지 않는 경우 오류를 발생
        # day ahead scheduling을 위해 program_end_hour 또는 length 중 하나를 제공
        if self.length != self.end_hour - self.start_hour + 1:
            TellUser.error(f'Demand Response: event length ({self.length}) is not program_end_hour ({self.end_hour}) - program_start_hour ({self.start_hour}). '
                            + 'This is ambiguous. '
                            + 'Please provide either program_end_hour or length for day ahead scheduling')
            raise ModelParameterError(f'Demand Response: event length ({self.length}) is not program_end_hour ({self.end_hour}) - program_start_hour ({self.start_hour}). '
                            + 'This is ambiguous. '
                            + 'Please provide either program_end_hour or length for day ahead scheduling')

    def grow_drop_data(self, years, frequency, load_growth):
        """ Update variable that hold timeseries data after adding growth data. These method should be called after
        add_growth_data and before the optimization is run.
        최적화가 실행되기 전에 시계열 데이터를 보관하는 변수를 업데이트

        Args:
            years (List): list of years for which analysis will occur on
            frequency (str): period frequency of the timeseries data
            load_growth (float): percent/ decimal value of the growth rate of loads in this simulation


        """
        # timeseries data
        self.system_load = Lib.fill_extra_data(self.system_load, years, load_growth, frequency)
        # 시계열 데이터에서 특정 연도 목록에 해당하지 않는 데이터를 제거
        self.system_load = Lib.drop_extra_data(self.system_load, years)

        # 시계열 데이터에서 주어진 연도 목록에 해당하지 않는 부분을 채움.
        self.months = Lib.fill_extra_data(self.months, years, 0, frequency)
        self.months = Lib.drop_extra_data(self.months, years)

        self.cap_commitment = Lib.fill_extra_data(self.cap_commitment, years, 0, frequency)
        self.cap_commitment = Lib.drop_extra_data(self.cap_commitment, years)

        # monthly data
        self.cap_monthly = Lib.fill_extra_data(self.cap_monthly, years, 0, 'M')
        self.cap_monthly = Lib.drop_extra_data(self.cap_monthly, years)

        self.cap_price = Lib.fill_extra_data(self.cap_price, years, 0, 'M')
        self.cap_price = Lib.drop_extra_data(self.cap_price, years)

        self.ene_price = Lib.fill_extra_data(self.ene_price, years, 0, 'M')
        self.ene_price = Lib.drop_extra_data(self.ene_price, years)

    def calculate_system_requirements(self, der_lst):
        """ Calculate the system requirements that must be meet regardless of what other value streams are active
        However these requirements do depend on the technology that are active in our analysis
        시스템 요구 사항을 계산
        Args:
            der_lst (list): list of the initialized DERs in our scenario

        """
       # 최대 방전 가능량 계산
        max_discharge_possible = self.qualifying_commitment(der_lst, self.length)

        if self.day_ahead:
             # 이벤트가 "하루 전"에 예약되면 이벤트의 정확한 시간을 알 수 있으므로 이에 맞게 계획할 수 있습니다.
            # if events are scheduled the "day ahead", exact time of the event is known and we can plan accordingly
            indx_dr_days = self.day_ahead_event_scheduling()
        else:
            # 절대적인 제약 대신 전력 예약
            # 이벤트가 "당일"에 예약되거나 이벤트의 시작 시간이 불확실한 경우 가능한 모든 시작에 대해 적용
            # power reservations instead of absolute constraints
            # if events are scheduled the "Day of", or if the start time of the event is uncertain, apply at every possible start
            indx_dr_days = self.day_of_event_scheduling()

        # 최소 충전 제약 계산
        qc = np.minimum(self.cap_commitment.loc[indx_dr_days].values, max_discharge_possible)
        self.qc = pd.Series(qc, index=indx_dr_days, name='DR Discharge Min (kW)')
        self.possible_event_times = indx_dr_days

        if self.day_ahead:
            # 하루 전에 이벤트가 예약되었을 경우
            self.der_dispatch_discharge_min_constraint = pd.Series(qc, index=indx_dr_days, name='DR Discharge Min (kW)')
            # requirement() : 요구사항을 나타내는 클래스. 함수가 실행될 때마다 새로운 객체가 생성되어 해당 리스트에 추가됨.
            self.system_requirements += [Requirement('der dispatch discharge', 'min', self.name, self.der_dispatch_discharge_min_constraint)]
        else:
            # 전력 예약이 아닌 경우
            self.qualifying_energy()

    def day_ahead_event_scheduling(self):
        """ If Dr events are scheduled with the STORAGE operator the day before the event, then the operator knows
        exactly when these events will occur.

        We need to make sure that the storage can perform, IF called upon, by making the battery can discharge atleast enough
        to meet the qualifying capacity and reserving enough energy to meet the full duration of the event
      우리는 저장소가 호출되면 수행할 수 있도록, 최소한 자격 용량을 충족시키기 위해 배터리가 충전할 수 있을 정도로 충분하게 방전할 수 있고,
    이벤트의 전체 기간을 충족시키기 위해 충분한 에너지를 예약할 수 있어야 합니다.
        START_HOUR is required. A user must also provide either END_HOUR or LENGTH

        Returns: index for when the qualifying capacity must apply

        """
        index = self.system_load.index
        he = index.hour + 1  # hour ending

        ##########################
        # FIND DR EVENTS: system load -> group by date -> filter by DR hours -> sum system load energy -> filter by top n days
        ##########################

        # dr 프로그램은 월 기준 및 시간이 프로그램 시간인 경우에 활성화됩니다.
        # dr program is active based on month and if hour is in program hours
        # & : and 연산자
        active = self.months & (he >= self.start_hour) & (he <= self.end_hour)

        # dr_weekends가 False인 경우 weekend을 활성 상태에서 제거합니다.
        # remove weekends from active datetimes if dr_weekends is False
        if not self.weekend:
            # active.index.weekday: active의 인덱스(날짜 및 시간)에서 요일을 추출. 월요일은 0, 일요일은 6으로 표시.
            # .astype('int64'): 불리언 값을 정수(0 또는 1)로 변환. True는 1로, False는 0으로 변환.
            active = active & (active.index.weekday < SATURDAY).astype('int64')

        # 1) system load, during ACTIVE time-steps from largest to smallest
        # active의 값이 True인 인덱스(날짜 및 시간)에 해당하는 시스템 부하 데이터만 선택
        load_during_active_events = self.system_load.loc[active]

        # 2) system load is groupby by date and summed and multiplied by DT
        # 활성 이벤트 동안의 시스템 부하를 날짜별로 그룹화하고, 각 그룹에 대해 에너지를 합산한 후, 시간 간격(self.dt)을 곱하여 에너지를 계산하는 코드
        sum_system_load_energy = load_during_active_events.groupby(by=load_during_active_events.index.date).sum() * self.dt

        # 3) sort the energy per event and select peak time-steps
        # find number of events in month where system_load is at peak during active hours: select only first DAYS number of timestamps, per month
        # .sort_values(ascending=False): 시스템 부하의 총 에너지를 내림차순으로 정렬
        # [:self.days]: 정렬된 결과 중 상위 n개의 날짜만 선택
        disp_days = sum_system_load_energy.sort_values(ascending=False)[:self.days]

        # create a mask that is true when ACTIVE is true and the date is in DISP_DAYS.INDEX
        # pd.Series(): pandas 라이브러리의 Series 클래스를 사용하여 시리즈를 생성
        # NumPy 라이브러리의 np.repeat() 함수를 사용하여 False 값을 가진 배열을 생성하고, 이 배열을 인덱스의 길이만큼 반복
        # 초기에는 모든 값이 False인 시리즈가 생성
        # 후속 코드에서 특정 조건을 충족할 때 True 값으로 업데이트
        active_event_mask = pd.Series(np.repeat(False, len(index)), index=index)
        for date in disp_days.index:
           # OR(|) 연산자
           # active_event_mask는 disp_days에 포함된 날짜 중에서 해당 조건을 만족하는 인덱스에 대해 True 값을 가지게 됨.
            active_event_mask = (index.date == date) & active | active_event_mask
        # create index for power constraint
        # active_event_mask에서 값이 True인 부분만 선택
        # .index: 선택된 부분에서 인덱스만 추출
        indx_dr_days = active_event_mask.loc[active_event_mask].index

        return indx_dr_days

    def day_of_event_scheduling(self):
        """ If the DR events are scheduled the day of, then the STORAGE operator must prepare for an event to occur
        everyday, to start at any time between the program START_HOUR and ending on END_HOUR for the duration of
        LENGTH.

        In this case there must be a power reservations because the storage might or might not be called, so there must
        be enough power capacity to provide for all services.
        모든 서비스를 제공할 충분한 전력 용량이 있어야 합니다.
        Returns: index for when the qualifying capacity must apply

        """

        ##########################
        # FIND DR EVENTS
        ##########################
        index = self.system_load.index
        he = index.hour + 1

        # dr program is active based on month and if hour is in program hours
        active = self.months & (he >= self.start_hour) & (he <= self.end_hour)

        # remove weekends from active datetimes if dr_weekends is False
        if not self.weekend:
            active = active & (active.index.weekday < SATURDAY).astype('int64')

        return active.loc[active].index

    @staticmethod
    def qualifying_commitment(der_lst, length):
        """

        Args:
            der_lst (list): list of the initialized DERs in our scenario
            length (int): length of the event

        NOTE: RA has this same method too  -HN

        """
        # 각 DER 인스턴스에 대해 qualifying_capacity 메서드를 호출하여 총 qualifying capacity 계산
        qc = sum(der_instance.qualifying_capacity(length) for der_instance in der_lst)
        return qc

    def qualifying_energy(self):
        """ Calculated the qualifying energy to be able to participate in an event.

        This function should be called after calculating the qualifying commitment.

        """
        qe = self.qc * self.length  # qualifying energy timeseries dataframe

        # only apply energy constraint whenever an event could start. So we need to get rid of the last (SELF.LENGTH*SELF.DT) - 1 timesteps per event
        last_start = self.end_hour - self.length  # this is the last time that an event can start
        # 시계열 데이터프레임 qe의 인덱스에서 시간 정보를 추출
        mask = qe.index.hour <= last_start

        self.qe = qe.loc[mask] # 시계열 데이터프레임 qe에서 조건(mask)을 충족하는 부분만을 선택

    def p_reservation_discharge_up(self, mask):
        """ the amount of discharge power in the up direction (supplying power up into the grid) that
        needs to be reserved for this value stream

        Args:
            mask (DataFrame): A boolean array that is true for indices corresponding to time_series data included
                    in the subs data set

        Returns: CVXPY parameter/variable

        """
        if not self.day_ahead:
            # make sure we will be able to discharge if called upon (in addition to other market services)
            subs = mask.loc[mask]
            # mask의 길이에 해당하는 0으로 채워진 배열을 생성
            # 특정 조건(mask)을 충족하는 인덱스에 대해 초기값이 0인 시리즈를 생성하는 코드
            dis_reservation = pd.Series(np.zeros(sum(mask)), index=subs.index)
            # self.qc의 인덱스 중에서 subs의 인덱스에 속하는 부분에 대해 True를 반환하는 불리언 시리즈를 생성
            subs_qc = self.qc.loc[self.qc.index.isin(subs.index)]
            if not subs_qc.empty:
                dis_reservation.update(subs_qc)
            down = cvx.Parameter(shape=sum(mask), value=dis_reservation.values, name='DischargeResDR')
        else:
          # Day-ahead 시나리오에서는 부모 클래스의 메서드를 호출
          # super() : 현재 클래스의 부모 클래스에 대한 참조를 반환
            down = super().p_reservation_discharge_up(mask)
        return down

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
        proforma = ValueStream.proforma_report(self, opt_years, apply_inflation_rate_func,
                                               fill_forward_func, results)
        proforma[self.name + ' Capacity Payment'] = 0
        proforma[self.name + ' Energy Payment'] = 0

        # 재 클래스의 속성인 possible_event_times에 해당하는 인덱스를 사용
        # 선택된 부분에서 'Total Storage Power (kW)' 열에 해당하는 데이터를 선택
        energy_displaced = results.loc[self.possible_event_times, 'Total Storage Power (kW)']
        energy_displaced += results.loc[self.possible_event_times, 'Total Generation (kW)']

        for year in opt_years:
            year_cap_price = self.cap_price.loc[self.cap_price.index.year == year]
            year_monthly_cap = self.cap_monthly.loc[self.cap_monthly.index.year == year]
            proforma.loc[pd.Period(year=year, freq='y'), self.name + ' Capacity Payment'] = \
                np.sum(np.multiply(year_monthly_cap, year_cap_price))

            if self.day_ahead:
                # in our "day of" event notification: the battery does not actually dispatch to
                # meet a DR event, so no $ is awarded
                year_subset = energy_displaced[energy_displaced.index.year == year]
                year_ene_price = self.ene_price.loc[self.ene_price.index.year == year]
                energy_payment = 0
                for month in range(1, 13):
                    energy_payment = \
                        np.sum(year_subset.loc[month == year_subset.index.month]) * year_ene_price.loc[year_ene_price.index.month == month].values
                proforma.loc[pd.Period(year=year, freq='y'), self.name + ' Energy Payment'] = \
                    energy_payment * self.dt
        # apply inflation rates
        proforma = apply_inflation_rate_func(proforma, None, min(opt_years))
        proforma = fill_forward_func(proforma, self.growth)
        return proforma

    def timeseries_report(self):
        """ Summaries the optimization results for this Value Stream.

        Returns: A timeseries dataframe with user-friendly column headers that summarize the results
            pertaining to this instance

        """
        report = pd.DataFrame(index=self.system_load.index)
        # 데이터프레임에 'System Load (kW)' 열을 추가하고 해당 열에 self.system_load 값을 할당
        report.loc[:, "System Load (kW)"] = self.system_load
        if self.day_ahead: # 'day_ahead' 속성이 True인 경우
            TellUser.info(f'Setting the "{self.der_dispatch_discharge_min_constraint.name}" to 0 in the output time series during non-events')
            report.loc[:, self.der_dispatch_discharge_min_constraint.name] = 0
            report.update(self.der_dispatch_discharge_min_constraint)
        else:
            report.loc[:, 'DR Possible Event (y/n)'] = False
            report.loc[self.possible_event_times, 'DR Possible Event (y/n)'] = True
        return report

    def monthly_report(self):
        """  Collects all monthly data that are saved within this object

        Returns: A dataframe with the monthly input price of the service

        """

        #  cap_price 속성을 이용하여 'DR Capacity Price ($/kW)' 열을 생성
        monthly_financial_result = pd.DataFrame({'DR Capacity Price ($/kW)': self.cap_price.values}, index=self.cap_price.index)
        monthly_financial_result.loc[:, 'DR Energy Price ($/kWh)'] = self.ene_price
        monthly_financial_result.index.names = ['Year-Month']

        return monthly_financial_result

    def update_price_signals(self, monthly_data, time_series_data):
        """ Updates attributes related to price signals with new price signals that are saved in
        the arguments of the method. Only updates the price signals that exist, and does not require all
        price signals needed for this service.

        Args:
            monthly_data (DataFrame): monthly data after pre-processing
            time_series_data (DataFrame): time series data after pre-processing

        """

       # 새로운 가격 신호로 필요한 속성만 업데이트하며, 필요 없는 경우에는 예외 처리를 통해 건너뜀.
        try:
            self.cap_price = monthly_data.loc[:, 'DR Capacity Price ($/kW)'] # DR Capacity Price ($/kW)' 열이 존재하는 경우, 해당 값을 사용하여 객체의 cap_price 속성을 업데이트
        except KeyError:
            pass

        try:
            self.ene_price = monthly_data.loc[:, 'DR Energy Price ($/kWh)'] # : 'DR Energy Price ($/kWh)' 열이 존재하는 경우, 해당 값을 사용하여 객체의 ene_price 속성을 업데이트
        except KeyError:
            pass
