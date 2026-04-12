import itertools
import random
from collections import Counter

import pandas as pd
import streamlit as st


POSITIONS = ["탑", "정글", "미드", "원딜", "서폿"]
POSITION_ORDER_MAP = {pos: i for i, pos in enumerate(POSITIONS)}


@st.cache_data
def load_data():
    df = pd.read_excel("player.xlsx")
    df.columns = df.columns.str.strip()

    for col in POSITIONS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ✅ 주포 / 부포 계산
def get_positions(row):
    scores = {pos: row[pos] for pos in POSITIONS if pd.notna(row[pos])}
    if not scores:
        return None, []

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    main_pos = sorted_scores[0][0]

    # 두 번째 점수
    if len(sorted_scores) > 1:
        second_score = sorted_scores[1][1]
        sub_positions = [pos for pos, score in sorted_scores if score == second_score]
    else:
        sub_positions = []

    return main_pos, sub_positions


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
            sub_pos_list = player["부포지션"]

            main_score = player[main_pos] if main_pos else score

            total_score += score

            if pos == main_pos:
                main_count += 1
            elif pos in sub_pos_list:
                offrole_penalty += float(main_score - score) * 0.5  # ⭐ 부포는 패널티 절반
            else:
                offrole_penalty += float(main_score - score)

            assignment.append({
                "이름": player["이름"],
                "포지션": pos,
                "점수": score,
                "주포지션": main_pos,
                "부포지션": ",".join(sub_pos_list) if sub_pos_list else "",
            })

        if not valid:
            continue

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
    df["정렬"] = df["포지션"].map(POSITION_ORDER_MAP)
    df = df.sort_values("정렬").reset_index(drop=True)
    return df[["포지션", "이름", "점수", "주포지션", "부포지션"]]


# ================= UI =================

st.set_page_config(page_title="내전 팀 메이커", layout="wide")

st.title("🎮 내전 5:5 팀 조합기")

df = load_data().copy()

# ⭐ 주포/부포 계산
df[["주포지션", "부포지션"]] = df.apply(lambda row: pd.Series(get_positions(row)), axis=1)

with st.sidebar:
    st.header("설정")

    max_diff = st.number_input("팀 점수 차이", 0.0, 5.0, 1.0)

    st.write("### 참여자 선택")

    selected_names = []
    cols = st.columns(2)

    for i, name in enumerate(df["이름"].tolist()):
        if cols[i % 2].checkbox(name):
            selected_names.append(name)

    st.write(f"{len(selected_names)} / 10")

    run_button = st.button("팀 생성")


if run_button:
    if len(selected_names) != 10:
        st.error("10명 선택하세요")
        st.stop()

    selected_df = df[df["이름"].isin(selected_names)].copy()

    st.subheader("선택된 10명")
    st.dataframe(selected_df[["이름"] + POSITIONS + ["주포지션", "부포지션"]])

    top_results = generate_top_combinations(selected_df, max_diff)

    st.subheader("TOP 5")

    for i, result in enumerate(top_results):
        st.write(f"### #{i+1} (차이 {result['diff']:.2f})")

        c1, c2 = st.columns(2)

        with c1:
            st.write("Team 1")
            st.dataframe(assignment_to_df(result["team1"]))

        with c2:
            st.write("Team 2")
            st.dataframe(assignment_to_df(result["team2"]))

    st.subheader("랜덤 추천")
    pick = random.choice(top_results)

    c1, c2 = st.columns(2)
    c1.dataframe(assignment_to_df(pick["team1"]))
    c2.dataframe(assignment_to_df(pick["team2"]))