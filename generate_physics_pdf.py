#!/usr/bin/env python3
"""Generate 9th Class Physics Chapter 3 (Dynamics) Notes PDF."""

from fpdf import FPDF
import os

class PhysicsNotesPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "9th Class Physics - Chapter 3: Dynamics", align="C")
        self.ln(4)
        self.set_draw_color(0, 102, 204)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def chapter_title(self, title):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(0, 51, 102)
        self.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 102, 204)
        self.set_line_width(0.8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def section_title(self, title):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(0, 102, 153)
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

    def formula(self, text):
        self.set_font("Courier", "B", 11)
        self.set_text_color(153, 0, 0)
        self.set_fill_color(245, 245, 245)
        self.cell(0, 8, f"  {text}", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.ln(2)

    def definition_box(self, term, definition):
        self.set_fill_color(230, 240, 255)
        self.set_draw_color(0, 102, 204)
        self.set_line_width(0.3)
        y_start = self.get_y()
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(0, 51, 102)
        self.cell(0, 7, f"  {term}", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(33, 33, 33)
        self.multi_cell(0, 5.5, f"  {definition}", fill=True)
        self.ln(3)

    def example_box(self, text):
        self.set_fill_color(255, 250, 230)
        self.set_draw_color(200, 150, 0)
        self.set_line_width(0.3)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(153, 102, 0)
        self.cell(0, 7, "  Example:", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(33, 33, 33)
        self.multi_cell(0, 5.5, f"  {text}", fill=True)
        self.ln(3)


def main():
    pdf = PhysicsNotesPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ==================== TITLE PAGE ====================
    pdf.add_page()
    pdf.ln(30)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 15, "9th Class Physics", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(0, 102, 204)
    pdf.cell(0, 12, "Chapter 3: Dynamics", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 10, "Comprehensive Study Notes", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_draw_color(0, 102, 204)
    pdf.set_line_width(1)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(15)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    topics = [
        "Force and its Types",
        "Newton's Laws of Motion",
        "Inertia and Mass",
        "Linear Momentum",
        "Friction",
        "Centripetal Force"
    ]
    for t in topics:
        pdf.cell(0, 8, f"  >  {t}", align="C", new_x="LMARGIN", new_y="NEXT")

    # ==================== CHAPTER 3 INTRO ====================
    pdf.add_page()
    pdf.chapter_title("Chapter 3: Dynamics")
    pdf.body_text(
        "Dynamics is the branch of mechanics that deals with the study of motion of objects "
        "and the forces acting on them. While Kinematics describes how objects move, Dynamics "
        "explains WHY they move - it studies the relationship between motion and the forces "
        "that cause it."
    )
    pdf.body_text(
        "The word 'Dynamics' comes from the Greek word 'dynamis' meaning force. In this "
        "chapter, we will explore the fundamental concepts of force, Newton's Laws of Motion, "
        "inertia, linear momentum, friction, and centripetal force."
    )

    # ==================== FORCE ====================
    pdf.section_title("3.1 Force")

    pdf.definition_box(
        "Force",
        "A force is a push or pull upon an object resulting from the object's interaction "
        "with another object. It is an external agent capable of changing the state of rest "
        "or state of motion of a body."
    )

    pdf.sub_section("Characteristics of Force:")
    pdf.bullet_point("Force is a vector quantity - it has both magnitude and direction.")
    pdf.bullet_point("Force can change the state of motion of an object (start, stop, speed up, slow down, change direction).")
    pdf.bullet_point("Force can change the shape of an object (deformation).")
    pdf.bullet_point("The SI unit of force is Newton (N).")
    pdf.bullet_point("1 Newton is the force that produces an acceleration of 1 m/s^2 in a body of mass 1 kg.")

    pdf.formula("1 N = 1 kg x 1 m/s^2")

    pdf.sub_section("Types of Forces:")

    pdf.sub_section("(a) Contact Forces:")
    pdf.body_text("Contact forces are forces that act only when objects are physically touching each other.")
    pdf.bullet_point("Muscular Force: Force applied by muscles of living beings (e.g., lifting a book, pushing a cart).")
    pdf.bullet_point("Frictional Force: Force that opposes the relative motion between two surfaces in contact.")
    pdf.bullet_point("Tension Force: Force transmitted through a string, rope, or cable when it is pulled tight.")
    pdf.bullet_point("Normal Force: The support force exerted upon an object that is in contact with another stable object.")
    pdf.bullet_point("Air Resistance: The frictional force air exerts against a solid body moving through it.")

    pdf.sub_section("(b) Non-Contact Forces:")
    pdf.body_text("Non-contact forces act even when objects are not physically touching.")
    pdf.bullet_point("Gravitational Force: The attractive force between any two objects having mass.")
    pdf.bullet_point("Electrostatic Force: Force between electrically charged particles.")
    pdf.bullet_point("Magnetic Force: Force exerted by magnets or moving electric charges.")

    pdf.example_box(
        "When you kick a football, the muscular force of your leg acts on the ball. "
        "The ball moves due to this applied force and eventually stops due to friction "
        "and air resistance acting against its motion."
    )

    # ==================== NEWTON'S LAWS ====================
    pdf.add_page()
    pdf.section_title("3.2 Newton's Laws of Motion")
    pdf.body_text(
        "Sir Isaac Newton (1642-1727) formulated three fundamental laws that describe the "
        "relationship between forces acting on a body and its motion. These laws form the "
        "foundation of classical mechanics."
    )

    # --- FIRST LAW ---
    pdf.sub_section("3.2.1 Newton's First Law of Motion (Law of Inertia)")
    pdf.definition_box(
        "Newton's First Law",
        "A body at rest remains at rest, and a body in uniform motion continues in that "
        "uniform motion in a straight line unless acted upon by an external unbalanced force."
    )

    pdf.body_text(
        "This law is also known as the Law of Inertia because it introduces the concept of "
        "inertia - the tendency of an object to resist changes in its state of motion."
    )

    pdf.sub_section("Key Points of First Law:")
    pdf.bullet_point("A stationary object will remain at rest unless acted upon by an unbalanced external force.")
    pdf.bullet_point("A moving object will continue to move in a straight line at constant speed unless acted upon by an unbalanced external force.")
    pdf.bullet_point("No object can change its state by itself - an external force is always required.")
    pdf.bullet_point("The law defines the concept of inertia.")

    pdf.example_box(
        "A book lying on a table remains at rest until someone picks it up. "
        "A ball rolling on a smooth surface continues to roll until friction or "
        "another force stops it."
    )

    # --- SECOND LAW ---
    pdf.add_page()
    pdf.sub_section("3.2.2 Newton's Second Law of Motion (Law of Acceleration)")
    pdf.definition_box(
        "Newton's Second Law",
        "The rate of change of linear momentum of a body is directly proportional to the "
        "applied external unbalanced force and takes place in the direction in which the "
        "force acts."
    )

    pdf.body_text("Mathematical Formulation:")
    pdf.formula("F = dp/dt  (where p = mv, linear momentum)")
    pdf.formula("F = ma  (for constant mass)")
    pdf.body_text("Where: F = Force (N), m = mass (kg), a = acceleration (m/s^2)")

    pdf.sub_section("Key Points of Second Law:")
    pdf.bullet_point("Force equals mass times acceleration: F = ma.")
    pdf.bullet_point("Greater force produces greater acceleration.")
    pdf.bullet_point("Greater mass means smaller acceleration for the same force.")
    pdf.bullet_point("Acceleration is in the same direction as the net force.")
    pdf.bullet_point("This law provides a quantitative measure of force.")
    pdf.bullet_point("Unit of force (Newton) is derived from this law.")

    pdf.example_box(
        "A force of 10 N applied to a 2 kg object produces an acceleration of 5 m/s^2. "
        "If the same force is applied to a 5 kg object, the acceleration will be only 2 m/s^2."
    )
    pdf.formula("a = F/m = 10/2 = 5 m/s^2")
    pdf.formula("a = F/m = 10/5 = 2 m/s^2")

    # --- THIRD LAW ---
    pdf.add_page()
    pdf.sub_section("3.2.3 Newton's Third Law of Motion (Law of Action-Reaction)")
    pdf.definition_box(
        "Newton's Third Law",
        "To every action, there is always an equal and opposite reaction. The action and "
        "reaction forces act on different bodies - never on the same body."
    )

    pdf.body_text(
        "Mathematically: If body A exerts force F on body B (action), then body B "
        "simultaneously exerts force -F on body A (reaction)."
    )

    pdf.sub_section("Key Points of Third Law:")
    pdf.bullet_point("Action and reaction forces are always equal in magnitude.")
    pdf.bullet_point("Action and reaction forces act in opposite directions.")
    pdf.bullet_point("Action and reaction forces act on different bodies (not on the same body).")
    pdf.bullet_point("Action and reaction forces always occur simultaneously.")
    pdf.bullet_point("Action and reaction forces are of the same nature (both gravitational, both contact, etc.).")
    pdf.bullet_point("Action and reaction forces cannot cancel each other (since they act on different bodies).")

    pdf.example_box(
        "When you push a wall (action), the wall pushes you back with equal force (reaction). "
        "When a gun fires a bullet, the bullet moves forward (action) and the gun recoils backward (reaction). "
        "A rocket launches by expelling gas downward (action), and the gas pushes the rocket upward (reaction)."
    )

    # ==================== INERTIA ====================
    pdf.add_page()
    pdf.section_title("3.3 Inertia and Mass")

    pdf.definition_box(
        "Inertia",
        "Inertia is the inherent property of a body by virtue of which it opposes any change "
        "in its state of rest or state of uniform motion in a straight line."
    )

    pdf.body_text(
        "Inertia is not a force - it is a property of matter. Every object in the universe "
        "possesses inertia. The greater the mass of an object, the greater its inertia, "
        "and the harder it is to change its state of motion."
    )

    pdf.sub_section("Types of Inertia:")

    pdf.sub_section("(a) Inertia of Rest:")
    pdf.body_text("The tendency of a body to remain at rest unless acted upon by an external force.")
    pdf.bullet_point("A passenger in a moving bus tends to fall backward when the bus suddenly starts.")
    pdf.bullet_point("A mango falls from a tree when shaken - the mango tends to stay at rest while the branch moves.")
    pdf.bullet_point("Dusting a carpet - carpet is beaten and dust continues to move due to inertia of rest.")

    pdf.sub_section("(b) Inertia of Motion:")
    pdf.body_text("The tendency of a body to continue in its state of uniform motion in a straight line.")
    pdf.bullet_point("A passenger in a moving bus tends to fall forward when the bus suddenly stops.")
    pdf.bullet_point("An athlete continues to run after reaching the finish line.")
    pdf.bullet_point("Passengers jump forward from a moving train when it stops suddenly.")

    pdf.sub_section("(c) Inertia of Direction:")
    pdf.body_text("The tendency of a body to continue in its direction of motion.")
    pdf.bullet_point("Mud thrown from spinning wheels of a vehicle flies off tangentially.")
    pdf.bullet_point("A stone tied to a string and whirled in a circle - if the string breaks, the stone flies off tangentially.")
    pdf.bullet_point("Passengers in a turning bus are pushed towards the outer side.")

    pdf.sub_section("Inertia and Mass:")
    pdf.body_text(
        "Mass is the quantitative measure of inertia. A body with greater mass has greater "
        "inertia. This is why it is harder to push or pull a heavy object (like a truck) "
        "compared to a light object (like a bicycle)."
    )
    pdf.formula("Greater Mass = Greater Inertia = More force needed to change motion")

    # ==================== LINEAR MOMENTUM ====================
    pdf.add_page()
    pdf.section_title("3.4 Linear Momentum")

    pdf.definition_box(
        "Linear Momentum",
        "Linear momentum of a body is the product of its mass and velocity. It is a vector "
        "quantity having the same direction as the velocity."
    )

    pdf.formula("p = m x v")
    pdf.body_text("Where: p = linear momentum (kg m/s), m = mass (kg), v = velocity (m/s)")

    pdf.sub_section("Key Points about Linear Momentum:")
    pdf.bullet_point("Momentum is a vector quantity - it has both magnitude and direction.")
    pdf.bullet_point("SI unit: kg m/s (kilogram meter per second).")
    pdf.bullet_point("A heavier body moving at the same speed has more momentum than a lighter body.")
    pdf.bullet_point("A body at rest has zero momentum (since v = 0).")
    pdf.bullet_point("Momentum is directly proportional to both mass and velocity.")

    pdf.sub_section("Newton's Second Law in Terms of Momentum:")
    pdf.body_text(
        "Newton's second law states that the rate of change of momentum of a body is "
        "proportional to the applied force and takes place in the direction of the force."
    )
    pdf.formula("F = dp/dt = d(mv)/dt")
    pdf.body_text("For constant mass:")
    pdf.formula("F = m x (dv/dt) = m x a")
    pdf.body_text(
        "This shows that force equals mass times acceleration, which is the most commonly "
        "used form of Newton's second law."
    )

    pdf.sub_section("Impulse and Momentum:")
    pdf.definition_box(
        "Impulse",
        "Impulse is the product of force and the time interval for which it acts. "
        "Impulse equals the change in momentum."
    )
    pdf.formula("J = F x dt = dp = change in momentum")
    pdf.body_text(
        "When the same change in momentum is produced in less time, the force required is "
        "greater. This is why air bags and crumple zones in cars reduce the force on passengers "
        "during a collision - they increase the time of impact."
    )

    pdf.example_box(
        "A cricket player pulls his hands backward while catching a ball. This increases "
        "the time of impact and reduces the force on his hands, preventing injury."
    )

    # ==================== FRICTION ====================
    pdf.add_page()
    pdf.section_title("3.5 Friction")

    pdf.definition_box(
        "Friction",
        "Friction is the force that opposes the relative motion (or tendency of such motion) "
        "between two surfaces in contact. It always acts in a direction opposite to the "
        "direction of motion (or intended motion)."
    )

    pdf.sub_section("Cause of Friction:")
    pdf.body_text(
        "Friction arises due to the interlocking of irregularities on the surfaces of two "
        "bodies in contact. Even surfaces that appear smooth have microscopic irregularities. "
        "When two surfaces are in contact, these irregularities interlock and resist relative "
        "motion."
    )

    pdf.sub_section("Types of Friction:")

    pdf.sub_section("(a) Static Friction:")
    pdf.body_text(
        "The frictional force that acts between two surfaces when there is no relative motion "
        "between them. It is a self-adjusting force that adjusts its value up to a maximum "
        "called limiting friction."
    )
    pdf.formula("f_s <= f_s(max) = mu_s x N")

    pdf.sub_section("(b) Kinetic (Sliding) Friction:")
    pdf.body_text(
        "The frictional force that acts between two surfaces when there is relative motion "
        "between them. It is always less than the limiting friction."
    )
    pdf.formula("f_k = mu_k x N")

    pdf.sub_section("(c) Rolling Friction:")
    pdf.body_text(
        "The frictional force that acts when a body rolls over another surface. Rolling "
        "friction is much smaller than sliding friction."
    )
    pdf.formula("f_r = mu_r x N")

    pdf.sub_section("Factors Affecting Friction:")
    pdf.bullet_point("Nature of surfaces: Rougher surfaces have more friction.")
    pdf.bullet_point("Normal force: Greater normal force means greater friction.")
    pdf.bullet_point("Contact area: Friction is generally independent of contact area (for rigid bodies).")
    pdf.bullet_point("State of motion: Sliding friction is less than static friction.")

    pdf.sub_section("Advantages of Friction:")
    pdf.bullet_point("Walking: We can walk because of friction between our shoes and the ground.")
    pdf.bullet_point("Writing: We can write because of friction between pen/chalk and surface.")
    pdf.bullet_point("Braking: Vehicles can stop due to friction between brake pads and wheels.")
    pdf.bullet_point("Holding: We can hold objects because of friction between our hands and the objects.")
    pdf.bullet_point("Nailing and screwing: Nails and screws stay in place due to friction.")

    pdf.sub_section("Disadvantages of Friction:")
    pdf.bullet_point("Energy loss: Friction converts useful mechanical energy into heat energy.")
    pdf.bullet_point("Wear and tear: Moving parts of machines wear out due to friction.")
    pdf.bullet_point("Reduced efficiency: Friction reduces the efficiency of machines.")
    pdf.bullet_point("Unwanted heat: Friction produces heat that can damage machinery.")

    pdf.sub_section("Methods to Reduce Friction:")
    pdf.bullet_point("Polishing: Smoothing surfaces reduces interlocking of irregularities.")
    pdf.bullet_point("Lubrication: Applying oil/grease creates a thin layer between surfaces.")
    pdf.bullet_point("Streamlining: Aerodynamic shapes reduce air resistance (drag).")
    pdf.bullet_point("Ball bearings: Convert sliding friction into rolling friction (much smaller).")
    pdf.bullet_point("Using wheels: Rolling friction is much less than sliding friction.")

    pdf.sub_section("Methods to Increase Friction:")
    pdf.bullet_point("Making surfaces rough (treads on tires, patterns on shoe soles).")
    pdf.bullet_point("Using adhesive materials (rubber soles, grip tape).")
    pdf.bullet_point("Increasing normal force (pressing surfaces together more firmly).")

    pdf.example_box(
        "A car moving at 60 km/h on a dry road needs a certain braking distance. On a wet "
        "road, the friction is reduced, so the braking distance increases significantly. "
        "This is why driving in rain is more dangerous."
    )

    # ==================== CENTRIPETAL FORCE ====================
    pdf.add_page()
    pdf.section_title("3.6 Centripetal Force")

    pdf.definition_box(
        "Centripetal Force",
        "Centripetal force is the net force acting on a body moving in a circular path. "
        "It is always directed towards the center of the circle. The word 'centripetal' "
        "means 'center-seeking'."
    )

    pdf.body_text(
        "When a body moves in a circular path, its direction of motion continuously changes. "
        "According to Newton's first law, this requires a force. The force that maintains "
        "circular motion is the centripetal force."
    )

    pdf.sub_section("Formula for Centripetal Force:")
    pdf.formula("F_c = mv^2 / r")
    pdf.body_text("Where: F_c = centripetal force (N), m = mass (kg), v = speed (m/s), r = radius of circular path (m)")

    pdf.sub_section("Characteristics of Centripetal Force:")
    pdf.bullet_point("It is always directed towards the center of the circular path.")
    pdf.bullet_point("It is perpendicular to the velocity of the body at any point.")
    pdf.bullet_point("It does no work on the body (since force is perpendicular to displacement).")
    pdf.bullet_point("It changes only the direction of velocity, not its magnitude.")
    pdf.bullet_point("It is a real force (not a fictitious force).")

    pdf.sub_section("Examples of Centripetal Force:")
    pdf.bullet_point("A stone tied to a string and whirled in a circle - tension in the string provides centripetal force.")
    pdf.bullet_point("Planets orbiting the Sun - gravitational force provides centripetal force.")
    pdf.bullet_point("A car turning on a road - friction between tires and road provides centripetal force.")
    pdf.bullet_point("Water in a rotating bucket - pressure difference provides centripetal force.")
    pdf.bullet_point("Electrons orbiting the nucleus - electrostatic force provides centripetal force.")

    pdf.sub_section("Centrifugal Force (Apparent Centripetal Force):")
    pdf.body_text(
        "Centrifugal force is the apparent outward force experienced by a body moving in a "
        "circular path when observed from the rotating frame of reference. It is not a real "
        "force but a pseudo force (fictitious force) that appears to act on the body due to "
        "the rotation of the reference frame."
    )
    pdf.formula("F_centrifugal = -F_centripetal (in rotating frame)")
    pdf.bullet_point("In a rotating car, passengers feel pushed outward - this is centrifugal force.")
    pdf.bullet_point("Clothes in a washing machine are pressed against the drum wall - centrifugal effect.")
    pdf.bullet_point("Water separates from wet clothes in a spin dryer due to centrifugal effect.")

    pdf.example_box(
        "A satellite orbits the Earth in a circular path. The gravitational force between "
        "the Earth and the satellite provides the centripetal force: F_g = F_c, i.e., "
    )
    pdf.formula("GMm/r^2 = mv^2/r => v = sqrt(GM/r)")

    # ==================== RELATIONS SUMMARY ====================
    pdf.add_page()
    pdf.section_title("3.7 Important Relations and Formulas Summary")

    pdf.sub_section("Force:")
    pdf.formula("F = ma")
    pdf.formula("1 N = 1 kg x 1 m/s^2")

    pdf.sub_section("Linear Momentum:")
    pdf.formula("p = mv")
    pdf.formula("F = dp/dt = d(mv)/dt")

    pdf.sub_section("Impulse:")
    pdf.formula("J = F x dt = dp")

    pdf.sub_section("Friction:")
    pdf.formula("f_s <= mu_s x N   (Static Friction)")
    pdf.formula("f_k = mu_k x N   (Kinetic Friction)")
    pdf.formula("f_r = mu_r x N   (Rolling Friction)")

    pdf.sub_section("Centripetal Force:")
    pdf.formula("F_c = mv^2 / r")

    pdf.sub_section("Newton's Laws Summary:")
    pdf.bullet_point("1st Law: F_net = 0 => constant velocity (v = constant)")
    pdf.bullet_point("2nd Law: F_net = ma = dp/dt")
    pdf.bullet_point("3rd Law: F_AB = -F_BA (action = -reaction)")

    pdf.sub_section("Conservation of Momentum:")
    pdf.formula("m1v1 + m2v2 = m1v1' + m2v2' (for isolated system)")

    # ==================== GLOSSARY ====================
    pdf.add_page()
    pdf.section_title("3.8 Glossary of Key Terms")

    terms = [
        ("Dynamics", "Branch of mechanics that studies motion and the forces causing it."),
        ("Force", "A push or pull that changes or tends to change the state of motion of a body."),
        ("Newton (N)", "SI unit of force. 1 N = 1 kg m/s^2."),
        ("Inertia", "The tendency of a body to resist any change in its state of motion."),
        ("Mass", "The quantity of matter in a body; measure of its inertia."),
        ("Momentum (p)", "Product of mass and velocity: p = mv. Vector quantity."),
        ("Impulse", "Product of force and time: J = Ft = change in momentum."),
        ("Static Friction", "Friction between surfaces when there is no relative motion."),
        ("Kinetic Friction", "Friction between surfaces when there is relative motion."),
        ("Coefficient of Friction (mu)", "Ratio of frictional force to normal force."),
        ("Centripetal Force", "Net force directed toward the center of a circular path."),
        ("Centrifugal Force", "Apparent outward force in a rotating frame of reference."),
        ("Action-Reaction Pair", "Two equal and opposite forces acting on different bodies."),
        ("Net Force", "Vector sum of all forces acting on a body."),
    ]

    for term, defn in terms:
        pdf.definition_box(term, defn)

    # ==================== PRACTICE QUESTIONS ====================
    pdf.add_page()
    pdf.section_title("3.9 Practice Questions")

    pdf.sub_section("Short Answer Questions:")
    questions = [
        "1. State Newton's three laws of motion.",
        "2. Define force. Give its SI unit.",
        "3. What is inertia? State its types.",
        "4. Define linear momentum. What is its SI unit?",
        "5. What is the difference between static and kinetic friction?",
        "6. What is centripetal force? Give its formula.",
        "7. Why does a moving car stop when brakes are applied?",
        "8. What is the relationship between mass and inertia?",
        "9. Explain why athletes run beyond the finish line.",
        "10. What is the difference between centripetal and centrifugal force?",
    ]
    for q in questions:
        pdf.bullet_point(q)

    pdf.ln(4)
    pdf.sub_section("Numerical Problems:")
    problems = [
        "1. A force of 20 N acts on a mass of 4 kg. Find the acceleration.",
        "2. A body of mass 5 kg is moving at 10 m/s. Calculate its momentum.",
        "3. A car of mass 1000 kg accelerates at 2 m/s^2. Find the net force acting on it.",
        "4. A force acts on a body for 5 s and changes its momentum by 50 kg m/s. Find the force.",
        "5. A body of mass 2 kg moves in a circle of radius 4 m at a speed of 6 m/s. Calculate the centripetal force.",
    ]
    for p in problems:
        pdf.bullet_point(p)

    # ==================== SAVE ====================
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    output_path = os.path.join(desktop, "9th_Physics_Chapter_3_Notes.pdf")
    pdf.output(output_path)
    print(f"PDF created successfully at: {output_path}")
    print(f"Total pages: {pdf.page_no()}")


if __name__ == "__main__":
    main()
