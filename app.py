import itertools
import random
from collections import Counter

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials


POSITIONS = ["탑", "정글", "미드", "원딜", "서폿"]


@st.cache_data
def load_data():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes,
    )
    client = gspread.authorize(creds)

    spreadsheet = client.open(st.secrets["google_sheet"]["spreadsheet_name"])
    worksheet = spreadsheet.worksheet(st.secrets["google_sheet"]["worksheet_name"])
    records = worksheet.get_all_records()

    df = pd.DataFrame(records)

    for col in POSITIONS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def get_main_position(row):
    scores = {pos: row[pos] for pos in POSITIONS if pd.notna(row[pos])}
    if not scores:
        return None
    return max(scores, key=scores.get)


def valid_positions(row):
    return [pos for pos in POSITIONS if pd.notna(row[pos])]


def assign_team_positions(team_df):
    players = team_df.to_dict("records")
    best_assignment = None
    best_score = None

    for perm in itertools.permutations(POSITIONS, 5):
        valid = True
        total_score = 0
        offrole_penalty = 0
        main_count = 0
        assignment = []

        for player, pos in zip(players, perm):
            if pd.isna(player[pos]):
                valid = False
                break

            score = float(player[pos])
            main_pos = player["주포지션"]
            main_score = player[main_pos] if main_pos and pd.notna(player[main_pos]) else score

            total_score += score
            if pos == main_pos:
                main_count += 1
            else:
                offrole_penalty += float(main_score - score)

            assignment.append({
                "소환명": player["소환명"],
                "이름": player["이름"],
                "포지션": pos,
                "점수": score,
                "주포지션": main_pos,
            })

        if not valid:
            continue

        # 점수함수: 주포지션 많이 갈수록 좋고, 부포 손실 적을수록 좋음
        heuristic = (-main_count, offrole_penalty, -total_score)

        if best_score is None or heuristic < best_score:
            best_score = heuristic
            best_assignment = {
                "assignment": assignment,
                "team_total": total_score,
                "main_count": main_count,
                "offrole_penalty": offrole_penalty,
            }

    return best_assignment


def team_main_position_conflict_penalty(team_df):
    counts = Counter(team_df["주포지션"])
    return sum(c - 1 for c in counts.values() if c > 1)


def evaluate_combination(team1_df, team2_df, max_diff=1.0):
    team1_result = assign_team_positions(team1_df)
    team2_result = assign_team_positions(team2_df)

    if not team1_result or not team2_result:
        return None

    diff = abs(team1_result["team_total"] - team2_result["team_total"])
    if diff > max_diff:
        return None

    conflict_penalty = (
        team_main_position_conflict_penalty(team1_df)
        + team_main_position_conflict_penalty(team2_df)
    )

    # 전체 조합 평가
    combo_score = (
        diff * 10
        + team1_result["offrole_penalty"]
        + team2_result["offrole_penalty"]
        + conflict_penalty * 0.5
        - (team1_result["main_count"] + team2_result["main_count"]) * 0.3
    )

    return {
        "team1": team1_result,
        "team2": team2_result,
        "diff": diff,
        "combo_score": combo_score,
    }


def generate_top_combinations(selected_df, max_diff=1.0, top_n=5):
    indices = list(selected_df.index)
    results = []

    # 중복 팀 분할 방지: 첫 번째 사람은 무조건 team1에 포함
    first_idx = indices[0]
    others = indices[1:]

    for comb in itertools.combinations(others, 4):
        team1_idx = [first_idx] + list(comb)
        team2_idx = [i for i in indices if i not in team1_idx]

        team1_df = selected_df.loc[team1_idx].copy()
        team2_df = selected_df.loc[team2_idx].copy()

        evaluated = evaluate_combination(team1_df, team2_df, max_diff=max_diff)
        if evaluated:
            results.append(evaluated)

    results.sort(key=lambda x: (x["combo_score"], x["diff"]))
    return results[:top_n]


def assignment_to_df(team_result):
    df = pd.DataFrame(team_result["assignment"])
    return df[["포지션", "소환명", "이름", "점수", "주포지션"]].sort_values("포지션")


st.set_page_config(page_title="내전 팀 메이커", layout="wide")

st.title("🎮 내전 5:5 팀 조합기")
st.caption("주포지션 우선, 빈 점수 라인 금지, 팀 점수 차이 제한")

df = load_data().copy()
df["주포지션"] = df.apply(get_main_position, axis=1)

with st.sidebar:
    st.header("설정")
    max_diff = st.number_input("팀 점수 차이 허용", min_value=0.0, max_value=5.0, value=1.0, step=0.1)

    participant_options = df["소환명"].tolist()
    selected_names = st.multiselect(
        "오늘 참여자 10명 선택",
        options=participant_options,
        default=participant_options[:10] if len(participant_options) >= 10 else participant_options,
    )

    run_button = st.button("TOP 5 조합 찾기", use_container_width=True)

if run_button:
    if len(selected_names) != 10:
        st.error("참여자는 정확히 10명을 선택해야 합니다.")
        st.stop()

    selected_df = df[df["소환명"].isin(selected_names)].copy()

    if len(selected_df) != 10:
        st.error("중복되었거나 시트 데이터 확인이 필요합니다.")
        st.stop()

    top_results = generate_top_combinations(selected_df, max_diff=max_diff, top_n=5)

    if not top_results:
        st.warning("조건을 만족하는 조합이 없습니다. 점수 차이 허용 범위를 조금 늘려보세요.")
        st.stop()

    st.subheader("🏆 TOP 5 조합")

    for i, result in enumerate(top_results, start=1):
        with st.container():
            st.markdown(f"### #{i}")
            c1, c2, c3 = st.columns(3)
            c1.metric("팀 점수 차이", f"{result['diff']:.2f}")
            c2.metric("팀1 총점", f"{result['team1']['team_total']:.2f}")
            c3.metric("팀2 총점", f"{result['team2']['team_total']:.2f}")

            left, right = st.columns(2)
            with left:
                st.markdown("#### Team 1")
                st.dataframe(assignment_to_df(result["team1"]), use_container_width=True)
            with right:
                st.markdown("#### Team 2")
                st.dataframe(assignment_to_df(result["team2"]), use_container_width=True)

            st.divider()

    st.subheader("🎲 랜덤 추천")
    picked = random.choice(top_results)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Random Team 1")
        st.dataframe(assignment_to_df(picked["team1"]), use_container_width=True)
    with c2:
        st.markdown("#### Random Team 2")
        st.dataframe(assignment_to_df(picked["team2"]), use_container_width=True)

    st.success(f"선택된 조합의 팀 점수 차이: {picked['diff']:.2f}")