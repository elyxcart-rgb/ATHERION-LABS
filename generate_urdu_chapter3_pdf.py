#!/usr/bin/env python3
"""Generate 9th Class Urdu Chapter 3 Notes PDF."""

from fpdf import FPDF
import os


class UrduNotesPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "9th Class Urdu - Chapter 3: Hazar Chashmeen", align="C")
        self.ln(4)
        self.set_draw_color(0, 153, 76)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def chapter_title(self, title):
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(0, 102, 51)
        self.cell(0, 14, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 153, 76)
        self.set_line_width(0.8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def section_title(self, title):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(0, 128, 64)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def sub_section(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(51, 51, 51)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(33, 33, 33)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet_point(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(33, 33, 33)
        x = self.get_x()
        self.cell(8, 5.5, "-")
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def definition_box(self, term, definition):
        self.set_fill_color(230, 245, 230)
        self.set_draw_color(0, 153, 76)
        self.set_line_width(0.3)
        y_start = self.get_y()
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(0, 80, 40)
        self.cell(0, 7, f"  {term}", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(33, 33, 33)
        self.multi_cell(0, 5.5, f"  {definition}", fill=True)
        self.ln(3)

    def poetry_line(self, text):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(0, 102, 153)
        self.cell(10, 6, ">>")
        self.multi_cell(0, 6, text)
        self.ln(1)

    def qa_box(self, question, answer):
        self.set_fill_color(255, 250, 230)
        self.set_draw_color(200, 150, 0)
        self.set_line_width(0.3)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(153, 102, 0)
        self.cell(0, 7, f"  Q: {question}", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(33, 33, 33)
        self.multi_cell(0, 5.5, f"  A: {answer}", fill=True)
        self.ln(3)


def main():
    pdf = UrduNotesPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ==================== TITLE PAGE ====================
    pdf.add_page()
    pdf.ln(25)
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(0, 102, 51)
    pdf.cell(0, 15, "9th Class Urdu", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(0, 153, 76)
    pdf.cell(0, 12, "Chapter 3: Hazar Chashmeen", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "Comprehensive Study Notes", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_draw_color(0, 153, 76)
    pdf.set_line_width(1)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(12)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(80, 80, 80)
    topics = [
        "Author: Rais Amrohvi",
        "Genre: Short Story (Afsana)",
        "Theme: Social Customs & Hypocrisy",
        "Key Characters & Analysis",
        "Vocabulary & Meanings",
        "Important Questions & Answers"
    ]
    for t in topics:
        pdf.cell(0, 8, f"  >  {t}", align="C", new_x="LMARGIN", new_y="NEXT")

    # ==================== CHAPTER INTRO ====================
    pdf.add_page()
    pdf.chapter_title("Chapter 3: Hazar Chashmeen")
    pdf.body_text(
        "\"Hazar Chashmeen\" (A Thousand Eyes) is a famous short story written by "
        "Rais Amrohvi (1914-1978), a renowned Pakistani journalist, writer, and poet. "
        "The story is a satirical masterpiece that exposes the hypocrisy prevalent in "
        "our society regarding customs and traditions."
    )
    pdf.body_text(
        "The story revolves around a family that faces a social dilemma when they need "
        "to arrange a marriage for their daughter. It highlights how people blindly follow "
        "customs without understanding their true meaning, leading to absurd situations."
    )
    pdf.body_text(
        "Rais Amrohvi was known for his sharp wit and ability to expose social evils "
        "through his writing. His real name was Muhammad Hussain Shahid, and he wrote "
        "extensively for newspapers and magazines."
    )

    # ==================== AUTHOR BIOGRAPHY ====================
    pdf.section_title("3.1 Author Biography")

    pdf.definition_box(
        "Rais Amrohvi (1914-1978)",
        "Full Name: Muhammad Hussain Shahid. He was a prominent Pakistani writer, "
        "journalist, and poet known for his satirical writing style. He contributed "
        "significantly to Urdu literature and journalism."
    )

    pdf.sub_section("Key Facts about the Author:")
    pdf.bullet_point("Born in Amroha, India in 1914")
    pdf.bullet_point("Migrated to Pakistan after partition in 1947")
    pdf.bullet_point("Famous for his column \"Khamosh\" in newspapers")
    pdf.bullet_point("Known as the father of Urdu journalism in Pakistan")
    pdf.bullet_point("Received several literary awards for his contributions")
    pdf.bullet_point("His writing style is characterized by irony and social criticism")
    pdf.bullet_point("He wrote short stories, essays, columns, and poetry")

    # ==================== STORY SUMMARY ====================
    pdf.add_page()
    pdf.section_title("3.2 Story Summary")

    pdf.sub_section("Plot Overview:")
    pdf.body_text(
        "The story begins with a family who needs to arrange the marriage of their "
        "daughter. According to local custom, before finalizing a marriage proposal, "
        "the girl must be examined by a doctor to ensure she is healthy and suitable "
        "for marriage."
    )
    pdf.body_text(
        "However, the family faces a peculiar problem. The custom requires that "
        "the girl be examined by not just one doctor, but by many doctors - hence "
        "the title \"Hazar Chashmeen\" (A Thousand Eyes). This custom has become "
        "so exaggerated that families spend enormous amounts of money and time "
        "getting their daughters examined by multiple doctors."
    )
    pdf.body_text(
        "The story takes a humorous turn when the family goes to extreme lengths "
        "to follow this custom. They visit doctor after doctor, each examining the "
        "girl and giving their opinion. The family becomes exhausted and frustrated "
        "but continues to follow the custom because they fear social criticism."
    )

    pdf.sub_section("Climax of the Story:")
    pdf.body_text(
        "The climax occurs when, after visiting numerous doctors, the family finally "
        "finds a doctor who refuses to participate in this absurd custom. The doctor "
        "points out the ridiculousness of the situation and questions the logic behind "
        "such customs. This moment serves as the turning point in the story."
    )

    pdf.sub_section("Resolution:")
    pdf.body_text(
        "The story ends with the realization that many of our customs and traditions "
        "are followed blindly without understanding their true purpose. The family "
        "learns that blind adherence to customs can lead to unnecessary problems and "
        "that common sense should be used when following traditions."
    )

    # ==================== CHARACTERS ====================
    pdf.add_page()
    pdf.section_title("3.3 Character Analysis")

    pdf.definition_box(
        "The Father",
        "The father is a middle-class man who wants to follow all customs to maintain "
        "his social reputation. He is willing to spend money and time to ensure his "
        "daughter's marriage goes smoothly according to tradition."
    )

    pdf.definition_box(
        "The Mother",
        "The mother is equally concerned about social customs and pressures. She "
        "supports her husband in following traditions but also feels the burden of "
        "the elaborate customs they must follow."
    )

    pdf.definition_box(
        "The Daughter",
        "The daughter is the central figure around whom the story revolves. She is "
        "a healthy young woman who becomes the subject of numerous medical examinations "
        "due to the custom. She represents the innocent victims of blind traditions."
    )

    pdf.definition_box(
        "The Doctor (Refusing Doctor)",
        "This character serves as the voice of reason in the story. He questions the "
        "absurd custom and represents rational thinking against blind tradition. His "
        "refusal to participate marks the turning point in the narrative."
    )

    # ==================== THEMES ====================
    pdf.add_page()
    pdf.section_title("3.4 Major Themes")

    pdf.sub_section("Theme 1: Blind Following of Customs")
    pdf.body_text(
        "The story primarily highlights how people follow customs and traditions "
        "without understanding their true purpose. The family in the story blindly "
        "follows the custom of getting their daughter examined by multiple doctors, "
        "even though it causes them great inconvenience and expense."
    )

    pdf.sub_section("Theme 2: Social Hypocrisy")
    pdf.body_text(
        "The story exposes the hypocrisy in society where people pretend to be "
        "respectable by following customs, but in reality, these customs often serve "
        "no practical purpose. The family's willingness to spend money and time on "
        "unnecessary examinations shows this hypocrisy."
    )

    pdf.sub_section("Theme 3: Cost of Following Traditions")
    pdf.body_text(
        "The story illustrates the financial and emotional cost of following blind "
        "traditions. The family spends significant money on doctor visits and "
        "examinations, all because of a custom that has lost its original meaning."
    )

    pdf.sub_section("Theme 4: Role of Common Sense")
    pdf.body_text(
        "The story emphasizes the importance of using common sense when following "
        "traditions. The doctor who refuses to participate represents the voice of "
        "reason and common sense in a situation dominated by blind tradition."
    )

    pdf.sub_section("Theme 5: Marriage Customs in Society")
    pdf.body_text(
        "The story specifically targets the elaborate marriage customs in South Asian "
        "society, where families go to extreme lengths to prove the suitability of "
        "their children for marriage, often at great personal cost."
    )

    # ==================== LITERARY DEVICES ====================
    pdf.add_page()
    pdf.section_title("3.5 Literary Devices Used")

    pdf.sub_section("1. Satire (Tanz-o-Hazal):")
    pdf.body_text(
        "The entire story is a satire on blind customs. The author uses humor and "
        "irony to expose the absurdity of traditions that people follow without "
        "questioning their relevance or necessity."
    )

    pdf.sub_section("2. Irony (Tanz):")
    pdf.body_text(
        "The irony in the story is that the family believes they are being responsible "
        "by following customs, but in reality, they are being foolish. The title itself "
        "is ironic - \"Hazar Chashmeen\" suggests many eyes watching, but no one is "
        "actually using their eyes to see the absurdity."
    )

    pdf.sub_section("3. Character Development:")
    pdf.body_text(
        "The author develops characters that represent different attitudes toward "
        "customs - the blind followers (parents), the innocent victim (daughter), "
        "and the voice of reason (the refusing doctor)."
    )

    pdf.sub_section("4. Dialogue:")
    pdf.body_text(
        "The story uses natural dialogue to reveal characters' attitudes and to "
        "advance the plot. The conversations between family members and doctors "
        "help expose the absurdity of the situation."
    )

    pdf.sub_section("5. Symbolism:")
    pdf.body_text(
        "The multiple medical examinations symbolize the unnecessary hurdles and "
        "burdens that society places on individuals in the name of tradition. "
        "The doctors represent various authorities who enforce these customs."
    )

    # ==================== VOCABULARY ====================
    pdf.add_page()
    pdf.section_title("3.6 Important Vocabulary")

    vocab = [
        ("Hazar Chashmeen", "A Thousand Eyes (title of the story)"),
        ("Afsana", "Short story"),
        ("Tanz-o-Hazal", "Satire and humor"),
        ("Rasm-o-Rivaj", "Customs and traditions"),
        ("Societal Hypocrisy", "Pretending to be respectable while following absurd customs"),
        ("Dowry System", "Custom of giving gifts/money at marriage"),
        ("Bride Price", "Money or gifts given to the bride's family"),
        ("Examination", "Medical check-up required by custom"),
        ("Common Sense", "Practical thinking and judgment"),
        ("Blind Following", "Following traditions without understanding"),
        ("Social Pressure", "Force of society to conform to customs"),
        ("Financial Burden", "Heavy cost of following traditions"),
        ("Absurdity", "Something completely irrational or ridiculous"),
        ("Satire", "Writing that uses humor to criticize or expose"),
        ("Customary Law", "Rules based on tradition rather than written law"),
        ("Auspicious", "Considered lucky or favorable"),
        ("Proposed Match", "Suggested marriage partner"),
        ("Family Honor", "Reputation of family in society"),
        ("Extravagance", "Spending too much money"),
        ("Impractical", "Not sensible or realistic"),
    ]

    for term, meaning in vocab:
        pdf.definition_box(term, meaning)

    # ==================== POETRY REFERENCE ====================
    pdf.add_page()
    pdf.section_title("3.7 Poetry References in Context")

    pdf.sub_section("Relevant Poetry Themes:")
    pdf.body_text(
        "While this chapter is primarily a prose story, the themes connect to "
        "various Urdu poetry traditions that critique society and customs."
    )

    pdf.poetry_line("Jo rasm-e-ulfat hai, woh kya hai? (What is this custom of love?)")
    pdf.poetry_line("Kuch to log kahenge, logon ka kaam hai kehna (People will say something, it is their job to say)")
    pdf.poetry_line("Rivajon ne qaid kar rakha hai (Customs have imprisoned us)")
    pdf.poetry_line("Aql ka fasaad hai, rivajon pe amal karna (It is madness to follow customs blindly)")

    pdf.ln(4)
    pdf.sub_section("Connection to Poetry:")
    pdf.body_text(
        "The story's theme of questioning blind traditions echoes sentiments found "
        "in the poetry of progressive poets who challenged societal norms and "
        "encouraged rational thinking over blind adherence to customs."
    )

    # ==================== Q&A ====================
    pdf.add_page()
    pdf.section_title("3.8 Important Questions & Answers")

    pdf.qa_box(
        "What is the main theme of \"Hazar Chashmeen\"?",
        "The main theme is the criticism of blind following of customs and traditions "
        "in society, particularly marriage customs that have become absurd and costly."
    )

    pdf.qa_box(
        "Who is the author of this story?",
        "The story is written by Rais Amrohvi (1914-1978), a famous Pakistani journalist, "
        "writer, and poet known for his satirical writing style."
    )

    pdf.qa_box(
        "Why is the story titled \"Hazar Chashmeen\"?",
        "The title literally means \"A Thousand Eyes\" and refers to the custom of getting "
        "the bride examined by many doctors (many eyes watching/judging) before marriage."
    )

    pdf.qa_box(
        "What is the irony in the story?",
        "The irony is that the family believes they are being responsible by following customs, "
        "but they are actually being foolish. No one questions the absurdity of the custom."
    )

    pdf.qa_box(
        "What message does the author want to convey?",
        "The author wants to convey that people should not follow customs blindly. They should "
        "use common sense and question traditions that have become absurd or impractical."
    )

    pdf.qa_box(
        "How does the story end?",
        "The story ends with a doctor refusing to participate in the absurd custom, serving as "
        "the voice of reason and questioning the blind adherence to traditions."
    )

    pdf.qa_box(
        "What role does satire play in this story?",
        "Satire is used throughout the story to expose the absurdity of blind customs. The "
        "humorous situations highlight how ridiculous such traditions can become."
    )

    pdf.qa_box(
        "How does the story relate to modern society?",
        "The story remains relevant today as many people still follow blind customs in marriage, "
        "education, and social life without questioning their necessity or practicality."
    )

    # ==================== SHORT ANSWER QUESTIONS ====================
    pdf.add_page()
    pdf.section_title("3.9 Short Answer Questions")

    short_questions = [
        "1. Write the name of the author and the title of the story.",
        "2. What custom is being followed in the story?",
        "3. Why does the family visit multiple doctors?",
        "4. What is the climax of the story?",
        "5. How does the doctor react to the custom?",
        "6. What lesson does the story teach us?",
        "7. Why is the story considered a satire?",
        "8. What is the significance of the title?",
        "9. Describe the character of the father.",
        "10. What social evil does the story expose?",
    ]
    for q in short_questions:
        pdf.bullet_point(q)

    pdf.ln(4)
    pdf.sub_section("Long Answer Questions:")
    long_questions = [
        "1. Summarize the story \"Hazar Chashmeen\" in your own words.",
        "2. Discuss the theme of blind following of customs with examples from the story.",
        "3. How does the author use satire to criticize society?",
        "4. Compare the attitudes of different characters toward customs.",
        "5. What message does the author convey through this story? Discuss.",
    ]
    for q in long_questions:
        pdf.bullet_point(q)

    # ==================== GLOSSARY ====================
    pdf.add_page()
    pdf.section_title("3.10 Glossary of Key Terms")

    terms = [
        ("Satire (Tanz)", "Literary device that uses humor, irony, or exaggeration to criticize and expose social evils."),
        ("Irony (Tanz)", "Expression of meaning through language that normally signifies the opposite, typically for humorous effect."),
        ("Custom (Rasm)", "A traditional and widely accepted way of behaving or doing something that is specific to a particular society or community."),
        ("Tradition (Rivaj)", "The transmission of customs or beliefs from generation to generation."),
        ("Hypocrisy", "The practice of claiming to have moral standards to which one's own behavior does not conform."),
        ("Social Norms", "Rules of behavior that are considered acceptable in a group or society."),
        ("Afsana", "Urdu term for short story, typically dealing with human emotions and social issues."),
        ("Prose (Nasar)", "Written or spoken language in its ordinary form, without metrical structure."),
        ("Dramatic Irony", "When the audience knows more than the characters in a story."),
        ("Social Criticism", "Writing that criticizes aspects of society and proposes improvement."),
        ("Moral Lesson", "The message or teaching that a story conveys to its readers."),
        ("Characterization", "The method used by an author to introduce and develop characters in a story."),
        ("Plot", "The main events of a story, especially as narrated or dealt with."),
        ("Setting", "The place and time where a story takes place."),
        ("Conflict", "The central struggle or problem in a story."),
        ("Resolution", "The part of a story where the main problem is solved."),
        ("Theme", "The main idea or underlying message of a story."),
        ("Symbolism", "The use of symbols to represent ideas or qualities."),
        ("Tone", "The author's attitude toward the subject matter."),
        ("Style", "The way in which an author writes."),
    ]

    for term, defn in terms:
        pdf.definition_box(term, defn)

    # ==================== SAVE ====================
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    output_path = os.path.join(desktop, "9th_Urdu_Chapter_3_Notes.pdf")
    pdf.output(output_path)
    print(f"PDF created successfully at: {output_path}")
    print(f"Total pages: {pdf.page_no()}")


if __name__ == "__main__":
    main()
