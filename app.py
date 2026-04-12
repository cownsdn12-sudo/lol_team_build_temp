import itertools
import random
from collections import Counter

import pandas as pd
import streamlit as st


POSITIONS = ["탑", "정글", "미드", "원딜", "서폿"]


# @st.cache_data
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
                offrole_penalty += float(main_score - score) * 0.5
            else:
                offrole_penalty += float(main_score - score)

            assignment.append({
                "이름": player["이름"],
                "포지션": pos,
                "점수": round(score, 2),
            })

        if not valid:
            continue

        heuristic = (-main_count, offrole_penalty, -total_score)

        if best_score is None or heuristic < best_score:
            best_score = heuristic
            best_assignment = {
                "assignment": assignment,
                "team_total": round(total_score, 2),
                "main_count": main_count,
                "offrole_penalty": round(offrole_penalty, 2),
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
        "diff": round(diff, 2),
        "combo_score": round(combo_score, 4),
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


def make_team_table(team1_result, team2_result):
    df1 = pd.DataFrame(team1_result["assignment"])
    df2 = pd.DataFrame(team2_result["assignment"])

    rows = []

    for pos in POSITIONS:
        row1 = df1[df1["포지션"] == pos]
        row2 = df2[df2["포지션"] == pos]

        rows.append({
            "포지션": pos,
            "1팀 이름": row1.iloc[0]["이름"] if not row1.empty else "",
            "1팀 점수": row1.iloc[0]["점수"] if not row1.empty else "",
            "2팀 이름": row2.iloc[0]["이름"] if not row2.empty else "",
            "2팀 점수": row2.iloc[0]["점수"] if not row2.empty else "",
        })

    return pd.DataFrame(rows)


st.set_page_config(page_title="내전 팀 메이커", layout="wide")

st.title("🎮 내전 5:5 팀 조합기")

df = load_data().copy()
df[["주포지션", "부포지션"]] = df.apply(lambda row: pd.Series(get_positions(row)), axis=1)

with st.sidebar:
    st.header("설정")
    max_diff = st.number_input("팀 점수 차이", min_value=0.0, max_value=5.0, value=1.0, step=0.1)

    st.write("### 참여자 선택 (정확히 10명)")

    selected_names = []
    all_names = df["이름"].tolist()

    current_selected_count = 0
    for name in all_names:
        if st.session_state.get(f"user_{name}", False):
            current_selected_count += 1

    cols = st.columns(2)

    for i, name in enumerate(all_names):
        checked = st.session_state.get(f"user_{name}", False)
        disable_checkbox = (current_selected_count >= 10 and not checked)

        if cols[i % 2].checkbox(
            name,
            key=f"user_{name}",
            disabled=disable_checkbox
        ):
            selected_names.append(name)

    selected_count = len(selected_names)
    st.write(f"{selected_count} / 10")

    if selected_count < 10:
        st.warning("10명을 모두 선택해야 팀 생성이 가능합니다.")
    elif selected_count == 10:
        st.success("10명 선택 완료")
    else:
        st.error("10명을 초과해서 선택할 수 없습니다.")

    run_button = st.button("팀 생성", use_container_width=True)


if run_button:
    if len(selected_names) < 10:
        st.error("10명을 모두 선택한 뒤 다시 실행하세요.")
        st.stop()

    if len(selected_names) > 10:
        st.error("10명까지만 선택할 수 있습니다.")
        st.stop()

    selected_df = df[df["이름"].isin(selected_names)].copy()

    if len(selected_df) != 10:
        st.error("선택 인원 확인 중 오류가 발생했습니다.")
        st.stop()

    st.subheader("선택된 10명")
    st.dataframe(
        selected_df[["이름"] + POSITIONS + ["주포지션", "부포지션"]].reset_index(drop=True),
        use_container_width=True
    )

    top_results = generate_top_combinations(selected_df, max_diff=max_diff, top_n=5)

    if not top_results:
        st.warning("조건을 만족하는 조합이 없습니다. 팀 점수 차이 범위를 조금 늘려보세요.")
        st.stop()

    st.subheader("TOP 5")

    for i, result in enumerate(top_results, start=1):
        st.markdown(f"### #{i}")
        c1, c2, c3 = st.columns(3)
        c1.metric("점수 차이", f"{result['diff']:.2f}")
        c2.metric("1팀 총점", f"{result['team1']['team_total']:.2f}")
        c3.metric("2팀 총점", f"{result['team2']['team_total']:.2f}")

        result_table = make_team_table(result["team1"], result["team2"])
        st.dataframe(result_table, use_container_width=True)
        st.divider()

    st.subheader("랜덤 추천")
    pick = random.choice(top_results)

    c1, c2, c3 = st.columns(3)
    c1.metric("점수 차이", f"{pick['diff']:.2f}")
    c2.metric("1팀 총점", f"{pick['team1']['team_total']:.2f}")
    c3.metric("2팀 총점", f"{pick['team2']['team_total']:.2f}")

    st.dataframe(make_team_table(pick["team1"], pick["team2"]), use_container_width=True)