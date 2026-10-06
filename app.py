import streamlit as st
import pandas as pd

# =========================
# 1. 页面标题
# =========================

st.title("📊 学生成绩分析系统")

st.write("欢迎使用学生成绩分析系统！")


# =========================
# 2. 侧边栏
# =========================

st.sidebar.title("📝 成绩输入")

name = st.sidebar.text_input(
    "姓名",
    "请输入姓名"
)

math = st.sidebar.number_input(
    "数学成绩",
    min_value=0,
    max_value=100,
    value=80
)

english = st.sidebar.number_input(
    "英语成绩",
    min_value=0,
    max_value=100,
    value=80
)

computer = st.sidebar.number_input(
    "计算机成绩",
    min_value=0,
    max_value=100,
    value=80
)


# =========================
# 3. 计算按钮
# =========================

if st.sidebar.button("📊 分析成绩"):

    # 计算平均分
    average = (math + english + computer) / 3

    # =========================
    # 4. 显示基本信息
    # =========================

    st.header(f"👤 {name} 的成绩分析")

    st.write(f"**平均分：{average:.2f}**")


    # =========================
    # 5. 判断等级
    # =========================

    if average >= 90:
        grade = "A"
        message = "优秀！🎉"

    elif average >= 80:
        grade = "B"
        message = "良好！👍"

    elif average >= 70:
        grade = "C"
        message = "不错，继续努力！"

    elif average >= 60:
        grade = "D"
        message = "刚刚及格，需要继续努力。"

    else:
        grade = "F"
        message = "需要加强学习。"


    # =========================
    # 6. 显示分析结果
    # =========================

    st.subheader("📋 分析结果")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("平均分", f"{average:.2f}")

    with col2:
        st.metric("等级", grade)

    with col3:
        st.write(message)


    # =========================
    # 7. 制作成绩数据表
    # =========================

    data = pd.DataFrame({
        "科目": ["数学", "英语", "计算机"],
        "成绩": [math, english, computer]
    })


    # =========================
    # 8. 显示成绩表格
    # =========================

    st.subheader("📋 成绩表")

    st.dataframe(
        data,
        hide_index=True,
        use_container_width=True
    )


    # =========================
    # 9. 柱状图
    # =========================

    st.subheader("📊 成绩柱状图")

    st.bar_chart(
        data,
        x="科目",
        y="成绩"
    )


    # =========================
    # 10. 根据平均分显示提示
    # =========================

    if average >= 60:
        st.success("✅ 恭喜你，考试及格！")

    else:
        st.error("❌ 很遗憾，你没有及格。")