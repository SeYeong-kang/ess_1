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
class Period:
    def __init__(self, number):
        self.number = number  # 기간의 번호 또는 식별자
        self.tier_list = [] # 해당 기간에 속한 티어들의 리스트
        self.highest_rate = 0 # 해당 기간에서 가장 높은 요금 비율을 저장하는 변수

 # 특정 기간에서 특정 티어의 정보 가져옴
    def get_tier(self, number):
        """"
        Args:
            number (Int): index for which tier to return

        Returns:
            self.tier_list (EnergyTier): tier based on argument index

        """
        return self.tier_list[number]

 # 새로운 티어를 추가
    def add(self, tier):
        """"
        Args:
            tier (EnergyTier): new tier to be appended to tier_list

        """
        self.tier_list.append(tier)
     
# 해당 기간의 정보 출력
    def tostring(self):
        """
        Pretty print

        """
        print("Period " + str(self.number) + "-------------------------=")

    def get_highest_rate(self):
        """
        Sets the highest rate out of the tier_list

        """
        for tier in self.tier_list:
         # 티어의 요금 비율이 None인 경우 무시
            if tier.get_rate() is None:
                continue
             # 현재 티어의 요금 비율이 기존의 highest_rate보다 높으면 업데이트
            elif tier.get_rate() > self.highest_rate:
                self.highest_rate = tier.get_rate()
