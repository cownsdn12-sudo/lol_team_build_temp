import itertools
import random
from collections import Counter

import pandas as pd
import streamlit as st


POSITIONS = ["탑", "정글", "미드", "원딜", "서폿"]


@st.cache_data
def load_data():
    df = pd.read_excel("player.xlsx")
    df.columns = df.columns.str.strip()

    for col in POSITIONS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def get_positions(row):
    scores = {pos: row[pos] for pos in POSITIONS if pd.notna(row[pos])}
    if not scores:
        return None, []

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    main_pos = sorted_scores[0][0]

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
                offrole_penalty += (main_score - score) * 0.5
            else:
                offrole_penalty += (main_score - score)

            assignment.append({
                "이름": player["이름"],
                "포지션": pos,
                "점수": score,
            })

        if not valid:
            continue

        heuristic = (-main_count, offrole_penalty, -total_score)

        if best_score is None or heuristic < best_score:
            best_score = heuristic
            best_assignment = {
                "assignment": assignment,
                "team_total": total_score,
            }

    return best_assignment


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

        team1_result = assign_team_positions(team1_df)
        team2_result = assign_team_positions(team2_df)

        if not team1_result or not team2_result:
            continue

        diff = abs(team1_result["team_total"] - team2_result["team_total"])
        if diff <= max_diff:
            results.append({
                "team1": team1_result,
                "team2": team2_result,
                "diff": diff
            })

    results.sort(key=lambda x: x["diff"])
    return results[:top_n]


# ⭐ 핵심: 이름 + 점수 포함 통합표
def make_match_table(team1, team2):
    df1 = pd.DataFrame(team1["assignment"])
    df2 = pd.DataFrame(team2["assignment"])

    rows = []

    for pos in POSITIONS:
        p1 = df1[df1["포지션"] == pos]
        p2 = df2[df2["포지션"] == pos]

        rows.append({
            "포지션": pos,
            "Team1 이름": p1["이름"].values[0] if not p1.empty else "",
            "Team1 점수": round(p1["점수"].values[0], 2) if not p1.empty else "",
            "Team2 이름": p2["이름"].values[0] if not p2.empty else "",
            "Team2 점수": round(p2["점수"].values[0], 2) if not p2.empty else "",
        })

    return pd.DataFrame(rows)


# ================= UI =================

st.title("내전 팀 짜기")

df = load_data()

df[["주포지션", "부포지션"]] = df.apply(lambda row: pd.Series(get_positions(row)), axis=1)

selected = st.multiselect("10명 선택", df["이름"].tolist())

if st.button("팀 생성"):

    if len(selected) != 10:
        st.error("10명 선택해야함")
        st.stop()

    selected_df = df[df["이름"].isin(selected)]

    results = generate_top_combinations(selected_df)

    st.subheader("TOP 5")

    for i, res in enumerate(results):
        st.write(f"### #{i+1} (차이 {res['diff']:.2f})")

        table = make_match_table(res["team1"], res["team2"])
        st.dataframe(table, use_container_width=True)

    st.subheader("랜덤 추천")

    pick = random.choice(results)
    st.dataframe(make_match_table(pick["team1"], pick["team2"]), use_container_width=True)